
import os
import requests
import json
import re
from urllib.parse import urlparse
import streamlit as st
from google.cloud import bigquery
from datetime import datetime
from duckduckgo_search import DDGS
from rapidfuzz import fuzz

# Configuration
PROJECT_ID = "gen-lang-client-0045947309"
CACHE_TABLE = "gen-lang-client-0045947309.rnic.cache_enrichissement"

def get_apollo_api_key():
    key = None
    if "APOLLO_API_KEY" in st.secrets:
        key = st.secrets["APOLLO_API_KEY"]
        print(f"DEBUG: Found Apollo API Key in st.secrets (starts with {key[:4]}...)")
    else:
        key = os.environ.get("APOLLO_API_KEY", None)
        if key:
            print(f"DEBUG: Found Apollo API Key in environment (starts with {key[:4]}...)")
        else:
            print("DEBUG: Apollo API Key NOT FOUND")
    return key

def get_bigquery_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)

def init_enrichment_cache():
    """Creates the enrichment cache table if it doesn't exist."""
    client = get_bigquery_client()
    query = f"""
        CREATE TABLE IF NOT EXISTS `{CACHE_TABLE}` (
            siret STRING,
            syndic_name STRING,
            domain STRING,
            domain_source STRING,
            apollo_org_id STRING,
            contacts_json STRING,
            last_enriched TIMESTAMP,
            confidence_score FLOAT64
        )
    """
    try:
        client.query(query).result()
    except Exception as e:
        print(f"Error creating enrichment cache: {e}")

class EnrichmentManager:
    def __init__(self):
        self.bq_client = get_bigquery_client()
        self.apollo_key = get_apollo_api_key()

    def clean_domain(self, url):
        """Extracts root domain from URL (e.g., https://www.foncia.com/fr -> foncia.com)"""
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain.lower()
        except:
            return None

    def get_cached_data(self, siret):
        try:
            query = f"SELECT * FROM `{CACHE_TABLE}` WHERE siret = '{siret}' LIMIT 1"
            df = self.bq_client.query(query).to_dataframe()
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception as e:
            print(f"Enrichment Cache Lookup Error: {e}")
        return None

    def save_to_cache(self, data):
        try:
            # Ensure timestamp logic suitable for BQ
            data['last_enriched'] = datetime.now().isoformat()
            if isinstance(data.get('contacts_json'), list) or isinstance(data.get('contacts_json'), dict):
                 data['contacts_json'] = json.dumps(data['contacts_json'])
            
            self.bq_client.insert_rows_json(CACHE_TABLE, [data])
        except Exception as e:
            print(f"Enrichment Cache Save Error: {e}")

    def web_search_syndic(self, name, city):
        """Step 1: Search for official website using DuckDuckGo."""
        # Minimal query: Name + City to find the business entity
        query = f"{name} {city}"
        print(f"Searching: {query}")
        
        try:
            with DDGS() as ddgs:
                # Use default backend (api) usually better for business entities than 'html' if 'html' fails
                results = list(ddgs.text(query, region="fr-fr", max_results=5))
                
                # Filter out garbage (Google Support, Government info pages)
                clean_results = []
                for r in results:
                    href = r.get('href', '')
                    if 'google.com' not in href and '.gouv.fr' not in href and 'societe.com' not in href:
                        clean_results.append(r)
                        
                return clean_results
        except Exception as e:
            print(f"Search Error: {e}")
            return []

    def validate_domain(self, candidate_url, syndic_name):
        """Step 2: Heuristic Validation of the domain."""
        domain = self.clean_domain(candidate_url)
        if not domain:
            return None, 0

        # Blacklist
        blacklist = ["pagesjaunes.fr", "societe.com", "linkedin.com", "facebook.com", "verif.com", "meilleursyndic.com", "yelp.fr", "google.com"]
        if any(bl in domain for bl in blacklist):
            return None, 0
            
        # Fuzzy Match Name vs Domain
        # Remove extension
        domain_name = domain.split('.')[0]
        # Simple name cleaning
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', syndic_name.lower())
        
        ratio = fuzz.partial_ratio(clean_name, domain_name)
        
        # Threshold
        if ratio > 65:
            return domain, ratio
        
        return None, ratio

    def search_apollo_org(self, domain=None, name=None):
        """Step 3a: Apollo Org Search using mixed_companies/search endpoint (most reliable)."""
        if not self.apollo_key: 
            print("DEBUG: Apollo search skipped - No API Key")
            return None
        
        print(f"DEBUG: Searching Apollo Org. Domain: {domain}, Name: {name}")
        url = "https://api.apollo.io/v1/mixed_companies/search"
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.apollo_key
        }
        
        org_id = None

        # 1. Try Domain Search if domain exists
        if domain:
            data_domain = {
                "q_organization_domains_list": [domain], # Note: List parameter format
                "page": 1,
                "per_page": 1
            }
            try:
                response = requests.post(url, headers=headers, json=data_domain, timeout=10)
                print(f"DEBUG: Apollo Org Search (Domain) Status: {response.status_code}")
                
                if response.status_code == 200:
                    res = response.json()
                    # Response contains 'accounts' or 'organizations'
                    items = res.get('organizations', []) or res.get('accounts', [])
                    if items:
                        # Prefer organization_id if available, fallback to id
                        item = items[0]
                        org_id = item.get('organization_id') or item.get('id')
                        print(f"DEBUG: Found Apollo Org ID by Domain: {org_id}")
                        return org_id
            except Exception as e:
                print(f"DEBUG: Apollo Org Domain Error: {e}")
        
        # 2. Fallback: Try Name Search
        # If domain lookup failed or no domain provided, use name
        search_name = name
        if not search_name and domain:
             search_name = domain.split('.')[0]
        
        if search_name and not org_id:
            print(f"DEBUG: Trying Name Search for: {search_name}")
            # For name search, mixed_companies might behave differently, let's stick to org search for name 
            # OR we can try q_organization_name param in mixed_companies if supported.
            # Safe bet: use the same endpoint but check params. 
            # Documentation often suggests q_organization_name for name search.
            
            data_name = {
                "q_organization_name": search_name,
                "page": 1,
                "per_page": 1
            } 
            try: 
                response_name = requests.post(url, headers=headers, json=data_name, timeout=10)
                if response_name.status_code == 200:
                    res_name = response_name.json()
                    items_name = res_name.get('organizations', []) or res_name.get('accounts', [])
                    if items_name:
                        item = items_name[0]
                        org_id = item.get('organization_id') or item.get('id')
                        print(f"DEBUG: Found Apollo Org ID by Name ({search_name}): {org_id}")
                        return org_id
                    else:
                        print(f"DEBUG: No Apollo Org found by Name either: {search_name}")
                else:
                    print(f"DEBUG: Apollo Org Search (Name) Failed: {response_name.status_code}")
            except Exception as e:
                print(f"DEBUG: Apollo Org Name Error: {e}")
        
        return None

    def search_apollo_people(self, org_id=None, domain=None):
        """Step 3b: Apollo People Search. Supports direct domain search or Org ID."""
        if not self.apollo_key: 
            print(f"DEBUG: Apollo people search skipped - No Key")
            return []
        
        if not org_id and not domain:
            print(f"DEBUG: Apollo people search skipped - No Org ID or Domain")
            return []

        print(f"DEBUG: Searching Apollo People. Org ID: {org_id}, Domain: {domain}")
        url = "https://api.apollo.io/v1/mixed_people/api_search"
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": self.apollo_key
        }
        
        # Titles to target
        titles = ["Gestionnaire", "Principal", "Directeur copropriété", "Syndic", "Gérant"]
        
        data = {
            "person_titles": titles,
            "page": 1,
            "per_page": 10
        }

        if domain:
            data["q_organization_domains_list"] = [domain]
        elif org_id:
            data["organization_ids"] = [org_id]
        
        contacts = []
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            print(f"DEBUG: Apollo People Search Status: {response.status_code}")
            if response.status_code == 200:
                people = response.json().get('people', [])
                print(f"DEBUG: Found {len(people)} people in Apollo")
                for p in people:
                    contacts.append({
                        "first_name": p.get("first_name") or "",
                        "last_name": p.get("last_name") or "",
                        "title": p.get("title") or "Unknown Title",
                        "email": p.get("email") or "",
                        "linkedin_url": p.get("linkedin_url") or "",
                        "photo_url": p.get("photo_url") or ""
                    })
            else:
                print(f"DEBUG: Apollo People Search Failed - Status: {response.status_code}, Content: {response.text[:200]}")
        except Exception as e:
            print(f"DEBUG: Apollo People Error: {e}")
            
        return contacts

    def enrich_syndic(self, siret, name, city, pappers_data=None):
        """
        Executes the full Sales Intelligence Pipeline for a Syndic.
        
        Flow:
        1. Cache Lookup: Checks BQ for existing enriched data.
        2. Domain Identification: 
           - Checks Pappers data (websites/email domains).
           - Executes DuckDuckGo web search if necessary.
        3. Domain Validation: Uses fuzzy matching to confirm the domain belongs to the target.
        4. Apollo Enrichment: 
           - Searches for official contacts by domain.
           - Falls back to organization name search if domain-based search fails.
        5. Cache Persistence: saves the final result to BigQuery.
        """
        
        # A. Check Cache
        cached = self.get_cached_data(siret)
        if cached:
            if isinstance(cached.get('contacts_json'), str):
                try:
                    cached['contacts_json'] = json.loads(cached['contacts_json'])
                except:
                    cached['contacts_json'] = []
            return cached

        best_domain = None
        best_score = 0
        source = "web_search"

        # B. Try Pappers Data (Website or Email Domain)
        if pappers_data:
            candidates = []
            
            # 1. Inspect 'sites_internet'
            sites = pappers_data.get('sites_internet', '')
            if sites:
                # Pappers can return "site1.com, site2.com". Split them.
                for s in sites.split(','):
                    candidates.append(s.strip())

            # 2. Inspect 'email'
            email = pappers_data.get('email', '')
            if email and '@' in email:
                email_domain = email.split('@')[-1].strip()
                # Ignore generic domains
                if email_domain not in ['gmail.com', 'orange.fr', 'wanadoo.fr', 'yahoo.fr', 'outlook.com', 'hotmail.fr', 'hotmail.com']:
                    candidates.append(email_domain)
            
            # Validate Candidates
            for cand in candidates:
                dom, score = self.validate_domain(cand, name)
                if dom and score > best_score:
                    best_domain = dom
                    best_score = score
                    source = "pappers_data"
        
        # C. Web Search Fallback (Only if Pappers failed)
        if not best_domain:
            print(f"DEBUG: Pappers fallback failed, launching web search for {name} in {city}")
            search_results = self.web_search_syndic(name, city)
            print(f"DEBUG: Web search returned {len(search_results)} results")
            for res in search_results:
                url = res.get('href', '')
                dom, score = self.validate_domain(url, name)
                print(f"DEBUG: Validating {url} -> Domain: {dom}, Score: {score}")
                if dom and score > best_score:
                    best_domain = dom
                    best_score = score
                    source = "web_search"
        
        # If no good domain found, we used to stop. Now we try Apollo with Name.
        if not best_domain:
            print(f"DEBUG: No valid domain found for {name}. Attempting Apollo Name Search directly.")
            source = "name_fallback"
            
        print(f"DEBUG: Best Domain found: {best_domain} (Source: {source}, Score: {best_score})")
 
        # D. Apollo Enrichment
        contacts = []
        if best_domain:
            # New direct strategy: Search people directly by domain
            contacts = self.search_apollo_people(domain=best_domain)
            
        # Fallback if no domain or no contacts found by domain
        if not contacts:
            print(f"DEBUG: No contacts found by domain. Attempting Org ID fallback.")
            org_id = self.search_apollo_org(domain=best_domain, name=name)
            if org_id:
                contacts = self.search_apollo_people(org_id=org_id)
            else:
                org_id = ""
        else:
            # If we found contacts by domain, we might still want the org_id for the cache
            # but searching by domain is already successful. Let's just set org_id to None or try a quick fetch if needed.
            # For simplicity, we can fetch org_id only if it's missing in the end result.
            org_id = "" # Will be filled by cache logic or kept empty
            
        # E. Save Result
        result = {
            "siret": siret,
            "syndic_name": name,
            "domain": best_domain,
            "domain_source": source,
            "apollo_org_id": org_id or "",
            "contacts_json": contacts,
            "confidence_score": float(best_score)
        }
        
        self.save_to_cache(result)
        return result

