
import os
import json
import re
import requests
import streamlit as st
from urllib.parse import urlparse
from google.cloud import bigquery
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from openai import OpenAI
from rapidfuzz import fuzz

PROJECT_ID = "gen-lang-client-0045947309"
CACHE_TABLE = "gen-lang-client-0045947309.rnic.cache_syndic_intel"
ANALYSIS_VERSION = 3
DEFAULT_TTL_DAYS = 30

# ── ScraperAPI Configuration ─────────────────────────────
SCRAPERAPI_KEY = st.secrets.get("SCRAPERAPI_KEY", os.environ.get("SCRAPERAPI_KEY", ""))
SCRAPERAPI_SERP_URL = "https://api.scraperapi.com/structured/google/search"
SCRAPERAPI_MAPS_URL = "https://api.scraperapi.com/structured/google/mapssearch"
SCRAPERAPI_SCRAPE_URL = "https://api.scraperapi.com"

URL_BLACKLIST = [
    "pagesjaunes.fr", "societe.com", "linkedin.com", "facebook.com",
    "verif.com", "meilleursyndic.com", "yelp.fr", "google.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com",
    "annuaire-entreprises.data.gouv.fr", "pappers.fr", "infogreffe.fr",
    "manageo.fr", "score3.fr", "entreprise.lefigaro.fr",
]

PAGE_BLACKLIST_KEYWORDS = [
    "annonce", "vente", "location", "actualite", "blog", "recrutement",
    "emploi", "presse", "newsletter", "mentions-legales", "politique-de-confidentialite",
    "cgu", "cgv", "cookies", "plan-du-site", "sitemap",
]

PAGE_PRIORITY_KEYWORDS = [
    "about", "propos", "equipe", "team", "service", "contact",
    "qui-sommes", "notre-cabinet", "notre-agence", "nos-metiers",
    "copropriete", "gestion", "syndic",
]

ANALYSIS_PROMPT = """Tu es un analyste B2B expert en syndics de copropriété français.
À partir des données collectées ci-dessous, produis un rapport d'intelligence commerciale structuré en JSON.

## Données légales (Pappers)
{legal_data}

## Contenu du site web
{website_content}

## Données Google Maps
{google_maps_data}

## Liens réseaux sociaux trouvés
{social_links}

## Avis et réputation en ligne
{reviews_data}

## Employés et contacts (Apollo)
{apollo_contacts}

## Contexte
Ce syndic gère {nb_copros} copropriétés représentant {total_lots} lots au total.
Nous cherchons à le prospecter pour des projets de rénovation énergétique (CEE - Certificats d'Économies d'Énergie).

## Instructions
1. Croise les données de toutes les sources pour vérifier la cohérence (téléphone, adresse, email).
2. Privilégie les données Google Maps et du site web pour le téléphone et l'email (plus fiables que Pappers).
3. Produis UNIQUEMENT un JSON valide (sans markdown, sans ```), avec cette structure exacte :
{{
  "resume_activite": "Description en 2-3 phrases de l'activité du syndic",
  "taille_estimee": "TPE ou PME ou ETI ou GE",
  "services_proposes": ["liste", "des", "services", "identifiés"],
  "zones_geographiques": ["zones", "couvertes"],
  "points_forts": ["3 atouts max identifiés pour la prospection CEE"],
  "points_faibles": ["3 faiblesses ou risques max"],
  "maturite_digitale": "faible ou moyenne ou forte",
  "reseaux_sociaux": {{
    "linkedin": {{"url": "", "actif": true, "description": ""}},
    "facebook": {{"url": "", "actif": false, "description": ""}},
    "instagram": {{"url": "", "actif": false, "description": ""}},
    "google_business": {{"url": "", "note": "", "nb_avis": ""}}
  }},
  "reputation_en_ligne": "Synthèse de la réputation en 1-2 phrases",
  "score_prospection": 7,
  "angle_approche_recommande": "Conseil personnalisé pour approcher ce syndic sur les CEE",
  "email_icebreaker": "Email de prospection personnalisé et professionnel (3-4 phrases max, tutoiement exclu)",
  "telephone_principal": "Numéro de téléphone principal du syndic (vérifié/croisé entre les sources)",
  "email_principal": "Email principal du syndic (vérifié/croisé entre les sources)",
  "adresse_principale": "Adresse principale du syndic (depuis Google Maps ou Pappers)",
  "contacts_cles": [
    {{
      "nom": "Prénom Nom",
      "poste": "Titre du poste",
      "email": "email si disponible",
      "telephone": "téléphone si disponible",
      "linkedin": "URL LinkedIn si disponible",
      "pertinence_cee": "Pourquoi cette personne est pertinente pour la prospection CEE"
    }}
  ]
}}"""


def _get_apollo_api_key():
    if "APOLLO_API_KEY" in st.secrets:
        return st.secrets["APOLLO_API_KEY"]
    return os.environ.get("APOLLO_API_KEY")


def get_openai_client():
    key = None
    if "OPENAI_API_KEY" in st.secrets:
        key = st.secrets["OPENAI_API_KEY"]
    else:
        key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAI(api_key=key)


def get_bigquery_client():
    if "GOOGLE_SERVICE_ACCOUNT_JSON" in st.secrets:
        info = dict(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
        return bigquery.Client.from_service_account_info(info)
    return bigquery.Client(project=PROJECT_ID)


def init_intel_cache():
    client = get_bigquery_client()
    query = f"""
        CREATE TABLE IF NOT EXISTS `{CACHE_TABLE}` (
            siret STRING,
            syndic_name STRING,
            raw_website_content STRING,
            social_links_json STRING,
            reviews_raw STRING,
            apollo_contacts_json STRING,
            scraped_phones STRING,
            scraped_emails STRING,
            llm_analysis_json STRING,
            llm_model_used STRING,
            last_analyzed TIMESTAMP,
            analysis_version INT64,
            cache_ttl_days INT64
        )
    """
    try:
        client.query(query).result()

        table = client.get_table(CACHE_TABLE)
        existing_cols = [schema.name for schema in table.schema]
        new_cols = {
            "google_maps_json": "STRING",
            "serp_results_json": "STRING",
            "identified_domain": "STRING",
            "domain_source": "STRING",
        }
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                alter_query = f"ALTER TABLE `{CACHE_TABLE}` ADD COLUMN {col} {col_type}"
                client.query(alter_query).result()
                print(f"Migration: Added column {col}")
    except Exception as e:
        print(f"Error creating/migrating intel cache: {e}")


class SyndicIntelligence:
    MAX_PAGES = 5
    MAX_CHARS_PER_PAGE = 8000
    SCRAPE_TIMEOUT = 30

    PHONE_RE = re.compile(
        r'(?:\+33[\s.]?|0)(?:[1-9])(?:[\s.\-]?\d{2}){4}'
    )
    EMAIL_RE = re.compile(
        r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
    )

    def __init__(self):
        self.bq_client = get_bigquery_client()
        self.openai_client = get_openai_client()
        self.apollo_key = _get_apollo_api_key()
        self.scraperapi_key = SCRAPERAPI_KEY

    # ── Cache ────────────────────────────────────────────────

    def get_cached_intel(self, siret):
        try:
            query = f"SELECT * FROM `{CACHE_TABLE}` WHERE siret = '{siret}' LIMIT 1"
            df = self.bq_client.query(query).to_dataframe()
            if df.empty:
                return None
            row = df.iloc[0].to_dict()
            if row.get("analysis_version") != ANALYSIS_VERSION:
                return None
            last = row.get("last_analyzed")
            ttl = row.get("cache_ttl_days") or DEFAULT_TTL_DAYS
            if last and (datetime.now() - last.replace(tzinfo=None)) > timedelta(days=ttl):
                return None
            for field in ("llm_analysis_json", "social_links_json", "apollo_contacts_json",
                          "scraped_phones", "scraped_emails", "google_maps_json", "serp_results_json"):
                val = row.get(field)
                if isinstance(val, str):
                    try:
                        row[field] = json.loads(val)
                    except Exception:
                        pass
            return row
        except Exception as e:
            print(f"Intel cache lookup error: {e}")
            return None

    def save_to_cache(self, data):
        try:
            data["last_analyzed"] = datetime.now().isoformat()
            data["analysis_version"] = ANALYSIS_VERSION
            data["cache_ttl_days"] = DEFAULT_TTL_DAYS
            row = dict(data)
            for field in ("llm_analysis_json", "social_links_json", "apollo_contacts_json",
                          "scraped_phones", "scraped_emails", "google_maps_json", "serp_results_json"):
                val = row.get(field)
                if isinstance(val, (dict, list)):
                    row[field] = json.dumps(val, ensure_ascii=False)
            self.bq_client.insert_rows_json(CACHE_TABLE, [row])
        except Exception as e:
            print(f"Intel cache save error: {e}")

    # ── ScraperAPI: Google SERP Search ────────────────────────

    def _serp_search(self, query_str, num_results=5):
        """Single Google SERP search via ScraperAPI. Returns list of organic results."""
        if not self.scraperapi_key:
            print("DEBUG: ScraperAPI key missing, skipping SERP search")
            return []
        try:
            params = {
                "api_key": self.scraperapi_key,
                "query": query_str,
                "tld": "fr",
                "country_code": "fr",
                "gl": "FR",
                "hl": "fr",
                "num": str(num_results),
            }
            resp = requests.get(SCRAPERAPI_SERP_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("organic_results", [])
            else:
                print(f"DEBUG: SERP search failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"DEBUG: SERP search error: {e}")
        return []

    def google_search(self, name):
        """Run 2 Google searches and return up to 5 deduplicated organic results."""
        queries = [
            f'"{name}"',
            f'"{name}" syndic copropriété',
        ]
        all_results = []
        seen_links = set()

        for q in queries:
            results = self._serp_search(q, num_results=5)
            for r in results:
                link = r.get("link", "")
                if not link or link in seen_links:
                    continue
                if any(bl in link.lower() for bl in URL_BLACKLIST):
                    continue
                seen_links.add(link)
                all_results.append({
                    "title": r.get("title", ""),
                    "link": link,
                    "snippet": r.get("snippet", ""),
                })
            if len(all_results) >= 5:
                break

        return all_results[:5]

    # ── ScraperAPI: Google Maps Search ────────────────────────

    def google_maps_search(self, name, city="", lat=None, lon=None):
        """Search Google Maps for the syndic and return structured data."""
        if not self.scraperapi_key:
            print("DEBUG: ScraperAPI key missing, skipping Maps search")
            return None
        latitude = lat or 48.8566
        longitude = lon or 2.3522
        query_str = f"{name} {city}".strip() if city else name

        try:
            params = {
                "api_key": self.scraperapi_key,
                "query": query_str,
                "latitude": str(latitude),
                "longitude": str(longitude),
            }
            resp = requests.get(SCRAPERAPI_MAPS_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    print(f"DEBUG: Google Maps returned 0 results for '{query_str}'")
                    return None

                best = self._find_best_maps_match(results, name)
                if best:
                    return {
                        "name": best.get("name", ""),
                        "address": best.get("address_line", ""),
                        "stars": best.get("stars"),
                        "ratings": best.get("ratings"),
                        "phone": best.get("phone", ""),
                        "url": best.get("url", ""),
                        "type": best.get("type", []),
                        "open": best.get("open", {}),
                    }
            else:
                print(f"DEBUG: Maps search failed ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"DEBUG: Maps search error: {e}")
        return None

    def _find_best_maps_match(self, results, name):
        """Find the best fuzzy match among Maps results."""
        clean_name = re.sub(r'[^a-zA-Z0-9\s]', '', name.lower())
        best_score = 0
        best_result = None
        for r in results[:10]:
            r_name = re.sub(r'[^a-zA-Z0-9\s]', '', (r.get("name") or "").lower())
            score = fuzz.partial_ratio(clean_name, r_name)
            if score > best_score:
                best_score = score
                best_result = r
        if best_score >= 50:
            return best_result
        return results[0] if results else None

    # ── ScraperAPI: Web Scraping (proxy) ──────────────────────

    def _extract_contact_info(self, soup):
        """Extract phones and emails from HTML."""
        phones = set()
        emails = set()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("tel:"):
                raw = href[4:].strip()
                raw = re.sub(r"[^\d+]", "", raw)
                if len(raw) >= 10:
                    phones.add(raw)
            elif href.startswith("mailto:"):
                addr = href[7:].split("?")[0].strip().lower()
                if "@" in addr:
                    emails.add(addr)

        full_text = soup.get_text(separator=" ", strip=True)
        for match in self.PHONE_RE.findall(full_text):
            cleaned = re.sub(r"[\s.\-]", "", match)
            if len(cleaned) >= 10:
                phones.add(cleaned)
        for match in self.EMAIL_RE.findall(full_text):
            addr = match.lower()
            generic = {"noreply", "no-reply", "mailer-daemon", "postmaster"}
            if not any(g in addr for g in generic):
                emails.add(addr)

        return list(phones), list(emails)

    def _is_useful_page(self, url):
        """Check if a URL is worth scraping (not an ad/blog/legal page)."""
        lower = url.lower()
        if any(kw in lower for kw in PAGE_BLACKLIST_KEYWORDS):
            return False
        return True

    def _is_priority_page(self, url):
        """Check if a URL is a high-priority page (about, contact, etc.)."""
        lower = url.lower()
        return any(kw in lower for kw in PAGE_PRIORITY_KEYWORDS)

    def _scrape_single_page(self, url):
        """Scrape a single page via ScraperAPI proxy."""
        if self.scraperapi_key:
            params = {
                "api_key": self.scraperapi_key,
                "url": url,
                "country_code": "fr",
            }
            return requests.get(SCRAPERAPI_SCRAPE_URL, params=params, timeout=self.SCRAPE_TIMEOUT)
        return requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }, timeout=self.SCRAPE_TIMEOUT, allow_redirects=True)

    def scrape_website(self, domain):
        """Scrape the syndic website using ScraperAPI as proxy."""
        if not domain:
            return "", [], []
        base_url = f"https://{domain}"
        all_text = []
        all_phones = set()
        all_emails = set()
        visited = set()
        to_visit = [base_url]

        while to_visit and len(visited) < self.MAX_PAGES:
            url = to_visit.pop(0)
            if url in visited:
                continue
            if not self._is_useful_page(url):
                continue
            visited.add(url)
            try:
                resp = self._scrape_single_page(url)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")

                page_phones, page_emails = self._extract_contact_info(soup)
                all_phones.update(page_phones)
                all_emails.update(page_emails)

                if len(visited) < self.MAX_PAGES:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("/"):
                            href = base_url + href
                        if domain in href and href not in visited and self._is_useful_page(href):
                            if self._is_priority_page(href):
                                to_visit.insert(0, href)
                            elif len(to_visit) < 10:
                                to_visit.append(href)

                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                    tag.decompose()

                page_text = soup.get_text(separator=" ", strip=True)
                page_text = re.sub(r"\s+", " ", page_text)[:self.MAX_CHARS_PER_PAGE]
                all_text.append(f"[PAGE: {url}]\n{page_text}")
            except Exception as e:
                print(f"DEBUG: Scrape error for {url}: {e}")
                continue

        content = "\n\n".join(all_text)[:30000]

        if all_phones or all_emails:
            content += "\n\n[CONTACTS EXTRAITS DU SITE WEB]"
            if all_phones:
                content += f"\nTéléphones trouvés : {', '.join(sorted(all_phones))}"
            if all_emails:
                content += f"\nEmails trouvés : {', '.join(sorted(all_emails))}"

        return content, list(all_phones), list(all_emails)

    # ── ScraperAPI: Social & Reputation (via Google SERP) ─────

    def search_social_presence(self, name, city=""):
        """Search for social media presence via Google SERP API."""
        results = {
            "linkedin": [],
            "facebook": [],
            "instagram": [],
            "google_business": [],
            "other": []
        }
        searches = [
            (f'"{name}" site:linkedin.com/company', "linkedin"),
            (f'"{name}" site:facebook.com', "facebook"),
        ]
        for query_str, category in searches:
            try:
                serp_results = self._serp_search(query_str, num_results=3)
                for r in serp_results:
                    results[category].append({
                        "title": r.get("title", ""),
                        "url": r.get("link", ""),
                        "snippet": r.get("snippet", "")[:200]
                    })
            except Exception:
                continue
        return results

    def search_reputation(self, name):
        """Search for online reputation via Google SERP API."""
        reviews_text = []
        queries = [
            f'"{name}" avis copropriété',
            f'"{name}" avis syndic',
        ]
        for query_str in queries:
            try:
                serp_results = self._serp_search(query_str, num_results=3)
                for r in serp_results:
                    reviews_text.append(f"- {r.get('title', '')}: {r.get('snippet', '')[:300]}")
            except Exception:
                continue
        return "\n".join(reviews_text)[:5000]

    # ── Domain Identification ─────────────────────────────────

    def _clean_domain(self, url):
        try:
            if not url.startswith('http'):
                url = 'https://' + url
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith('www.'):
                domain = domain[4:]
            return domain.lower()
        except Exception:
            return None

    def identify_domain(self, serp_results, name, pappers_data=None, maps_data=None):
        """Identify the best domain from SERP results, Pappers, and Maps data."""
        candidates = []

        if pappers_data:
            sites = pappers_data.get('sites_internet', '')
            if sites:
                for s in sites.split(','):
                    d = self._clean_domain(s.strip())
                    if d:
                        candidates.append(("pappers", d))
            email = pappers_data.get('email', '')
            if email and '@' in email:
                email_domain = email.split('@')[-1].strip()
                generic = ['gmail.com', 'orange.fr', 'wanadoo.fr', 'yahoo.fr', 'outlook.com', 'hotmail.fr', 'hotmail.com']
                if email_domain not in generic:
                    candidates.append(("pappers_email", email_domain))

        if maps_data and maps_data.get("url"):
            d = self._clean_domain(maps_data["url"])
            if d and not any(bl in d for bl in URL_BLACKLIST):
                candidates.append(("google_maps", d))

        for r in serp_results:
            d = self._clean_domain(r.get("link", ""))
            if d and not any(bl in d for bl in URL_BLACKLIST):
                candidates.append(("serp", d))

        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
        best_domain = None
        best_score = 0
        best_source = "unknown"

        for source, domain in candidates:
            domain_name = domain.split('.')[0]
            score = fuzz.partial_ratio(clean_name, domain_name)
            source_bonus = {"pappers": 10, "google_maps": 8, "pappers_email": 5, "serp": 0}.get(source, 0)
            total = score + source_bonus
            if total > best_score:
                best_score = total
                best_domain = domain
                best_source = source

        if best_score >= 55:
            return best_domain, best_source
        return None, "none"

    # ── Apollo Contacts ──────────────────────────────────────

    def _fetch_apollo_contacts(self, domain=None, name=None):
        if not self.apollo_key:
            print("DEBUG: Apollo skipped in intel - No API Key")
            return []

        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.apollo_key
        }

        org_id = None

        if domain:
            try:
                resp = requests.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    headers=headers,
                    json={"q_organization_domains_list": [domain], "page": 1, "per_page": 1},
                    timeout=10,
                )
                if resp.status_code == 200:
                    items = resp.json().get("organizations", []) or resp.json().get("accounts", [])
                    if items:
                        org_id = items[0].get("organization_id") or items[0].get("id")
            except Exception as e:
                print(f"DEBUG: Apollo org domain error: {e}")

        if not org_id and name:
            try:
                resp = requests.post(
                    "https://api.apollo.io/v1/mixed_companies/search",
                    headers=headers,
                    json={"q_organization_name": name, "page": 1, "per_page": 1},
                    timeout=10,
                )
                if resp.status_code == 200:
                    items = resp.json().get("organizations", []) or resp.json().get("accounts", [])
                    if items:
                        org_id = items[0].get("organization_id") or items[0].get("id")
            except Exception as e:
                print(f"DEBUG: Apollo org name error: {e}")

        if not org_id and not domain:
            return []

        search_data = {"page": 1, "per_page": 25}
        if domain:
            search_data["q_organization_domains_list"] = [domain]
        elif org_id:
            search_data["organization_ids"] = [org_id]

        contacts = []
        try:
            resp = requests.post(
                "https://api.apollo.io/v1/mixed_people/api_search",
                headers=headers,
                json=search_data,
                timeout=15,
            )
            if resp.status_code == 200:
                people = resp.json().get("people", [])
                for p in people:
                    phones = []
                    for ph in (p.get("phone_numbers") or []):
                        number = ph.get("sanitized_number") or ph.get("number") or ph.get("raw_number", "")
                        if number:
                            phones.append(number)
                    contacts.append({
                        "first_name": p.get("first_name") or "",
                        "last_name": p.get("last_name") or "",
                        "title": p.get("title") or "",
                        "email": p.get("email") or "",
                        "phone_numbers": phones,
                        "linkedin_url": p.get("linkedin_url") or "",
                        "city": p.get("city") or "",
                        "department": p.get("departments", [""])[0] if p.get("departments") else "",
                    })
                print(f"DEBUG: Apollo intel found {len(contacts)} contacts")
        except Exception as e:
            print(f"DEBUG: Apollo people search error: {e}")

        return contacts

    # ── LLM Analysis ─────────────────────────────────────────

    def analyze_with_llm(self, website_content, social_links, reviews_data, legal_data,
                         apollo_contacts=None, google_maps_data=None, nb_copros=0, total_lots=0):
        if not self.openai_client:
            return self._fallback_analysis(social_links, legal_data, apollo_contacts, google_maps_data)

        contacts_summary = "Aucun contact trouvé"
        if apollo_contacts:
            lines = []
            for c in apollo_contacts[:15]:
                parts = [f"{c.get('first_name', '')} {c.get('last_name', '')} - {c.get('title', 'N/A')}"]
                if c.get("email"):
                    parts.append(f"Email: {c['email']}")
                if c.get("phone_numbers"):
                    parts.append(f"Tél: {', '.join(c['phone_numbers'])}")
                if c.get("linkedin_url"):
                    parts.append(f"LinkedIn: {c['linkedin_url']}")
                lines.append(" | ".join(parts))
            contacts_summary = "\n".join(lines)

        maps_summary = "Non disponible"
        if google_maps_data:
            parts = []
            if google_maps_data.get("name"):
                parts.append(f"Nom: {google_maps_data['name']}")
            if google_maps_data.get("address"):
                parts.append(f"Adresse: {google_maps_data['address']}")
            if google_maps_data.get("phone"):
                parts.append(f"Téléphone: {google_maps_data['phone']}")
            if google_maps_data.get("stars") is not None:
                parts.append(f"Note Google: {google_maps_data['stars']}/5 ({google_maps_data.get('ratings', 0)} avis)")
            if google_maps_data.get("url"):
                parts.append(f"Site web: {google_maps_data['url']}")
            if google_maps_data.get("open"):
                parts.append(f"Horaires: {json.dumps(google_maps_data['open'], ensure_ascii=False)}")
            maps_summary = "\n".join(parts)

        prompt = ANALYSIS_PROMPT.format(
            legal_data=json.dumps(legal_data, ensure_ascii=False, default=str) if legal_data else "Non disponible",
            website_content=website_content[:15000] if website_content else "Site web non accessible",
            google_maps_data=maps_summary,
            social_links=json.dumps(social_links, ensure_ascii=False) if social_links else "Aucun réseau social trouvé",
            reviews_data=reviews_data if reviews_data else "Aucun avis trouvé",
            apollo_contacts=contacts_summary,
            nb_copros=nb_copros,
            total_lots=total_lots,
        )

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Tu es un analyste B2B. Réponds uniquement en JSON valide."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=3000,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except Exception as e:
            print(f"LLM analysis error: {e}")
            return self._fallback_analysis(social_links, legal_data, apollo_contacts, google_maps_data)

    def _fallback_analysis(self, social_links, legal_data, apollo_contacts=None, google_maps_data=None):
        contacts_cles = []
        if apollo_contacts:
            for c in apollo_contacts[:5]:
                contacts_cles.append({
                    "nom": f"{c.get('first_name', '')} {c.get('last_name', '')}",
                    "poste": c.get("title", ""),
                    "email": c.get("email", ""),
                    "telephone": ", ".join(c.get("phone_numbers", [])),
                    "linkedin": c.get("linkedin_url", ""),
                    "pertinence_cee": "",
                })

        tel = ""
        email = ""
        address = ""
        if google_maps_data:
            tel = google_maps_data.get("phone", "") or ""
            address = google_maps_data.get("address", "") or ""
        if legal_data:
            if not tel:
                tel = legal_data.get("telephone", "") or ""
            email = legal_data.get("email", "") or ""

        return {
            "resume_activite": f"Syndic de copropriété - {legal_data.get('denomination', 'N/A') if legal_data else 'N/A'}",
            "taille_estimee": "N/A",
            "services_proposes": [],
            "zones_geographiques": [],
            "points_forts": [],
            "points_faibles": ["Analyse LLM indisponible"],
            "maturite_digitale": "N/A",
            "reseaux_sociaux": social_links or {},
            "reputation_en_ligne": "Non analysée",
            "score_prospection": 5,
            "angle_approche_recommande": "Approche standard CEE",
            "email_icebreaker": "",
            "telephone_principal": tel,
            "email_principal": email,
            "adresse_principale": address,
            "contacts_cles": contacts_cles,
        }

    # ── Main Pipeline ────────────────────────────────────────

    def run_intelligence(self, siret, name, city="", domain=None, pappers_data=None,
                         nb_copros=0, total_lots=0, force_refresh=False, lat=None, lon=None):
        if not force_refresh:
            cached = self.get_cached_intel(siret)
            if cached:
                return cached

        # 1. Google SERP: 2 searches -> up to 5 organic results
        print(f"DEBUG: [1/7] Google SERP search for '{name}'")
        serp_results = self.google_search(name)
        print(f"DEBUG: SERP returned {len(serp_results)} results")

        # 2. Google Maps: search for business listing
        print(f"DEBUG: [2/7] Google Maps search for '{name}' in '{city}'")
        maps_data = self.google_maps_search(name, city, lat=lat, lon=lon)
        print(f"DEBUG: Maps data: {'found' if maps_data else 'not found'}")

        # 3. Identify domain from all sources
        print(f"DEBUG: [3/7] Identifying domain (provided: {domain})")
        if not domain:
            domain, domain_source = self.identify_domain(serp_results, name, pappers_data, maps_data)
            print(f"DEBUG: Identified domain: {domain} (source: {domain_source})")
        else:
            domain_source = "provided"

        # 4. Scrape website via ScraperAPI proxy
        print(f"DEBUG: [4/7] Scraping website: {domain}")
        website_content, scraped_phones, scraped_emails = self.scrape_website(domain)
        print(f"DEBUG: Scraped {len(website_content)} chars, {len(scraped_phones)} phones, {len(scraped_emails)} emails")

        # 5. Social presence via Google SERP
        print(f"DEBUG: [5/7] Social presence search")
        social_links = self.search_social_presence(name, city)

        # 6. Reputation via Google SERP
        print(f"DEBUG: [6/7] Reputation search")
        reviews_data = self.search_reputation(name)

        # 7. Apollo contacts (unchanged)
        print(f"DEBUG: [7/7] Apollo contacts")
        apollo_contacts = self._fetch_apollo_contacts(domain, name)

        # LLM Analysis with all enriched data
        print(f"DEBUG: Running LLM analysis...")
        llm_analysis = self.analyze_with_llm(
            website_content=website_content,
            social_links=social_links,
            reviews_data=reviews_data,
            legal_data=pappers_data,
            apollo_contacts=apollo_contacts,
            google_maps_data=maps_data,
            nb_copros=nb_copros,
            total_lots=total_lots,
        )

        result = {
            "siret": siret,
            "syndic_name": name,
            "raw_website_content": website_content[:50000],
            "social_links_json": social_links,
            "reviews_raw": reviews_data[:10000],
            "apollo_contacts_json": apollo_contacts,
            "llm_analysis_json": llm_analysis,
            "llm_model_used": "gpt-4o-mini",
            "scraped_phones": scraped_phones,
            "scraped_emails": scraped_emails,
            "google_maps_json": maps_data,
            "serp_results_json": serp_results,
            "identified_domain": domain or "",
            "domain_source": domain_source,
        }

        self.save_to_cache(result)
        return result
