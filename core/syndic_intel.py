
import os
import json
import re
import requests
import streamlit as st
from google.cloud import bigquery
from datetime import datetime, timedelta
from duckduckgo_search import DDGS
from bs4 import BeautifulSoup
from openai import OpenAI

PROJECT_ID = "gen-lang-client-0045947309"
CACHE_TABLE = "gen-lang-client-0045947309.rnic.cache_syndic_intel"
ANALYSIS_VERSION = 2
DEFAULT_TTL_DAYS = 30

ANALYSIS_PROMPT = """Tu es un analyste B2B expert en syndics de copropriété français.
À partir des données collectées ci-dessous, produis un rapport d'intelligence commerciale structuré en JSON.

## Données légales (Pappers)
{legal_data}

## Contenu du site web
{website_content}

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
Produis UNIQUEMENT un JSON valide (sans markdown, sans ```), avec cette structure exacte :
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
  "telephone_principal": "Numéro de téléphone principal du syndic (depuis Pappers ou Apollo)",
  "email_principal": "Email principal du syndic (depuis Pappers ou Apollo)",
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
            llm_analysis_json STRING,
            llm_model_used STRING,
            last_analyzed TIMESTAMP,
            analysis_version INT64,
            cache_ttl_days INT64
        )
    """
    try:
        client.query(query).result()
    except Exception as e:
        print(f"Error creating intel cache: {e}")


class SyndicIntelligence:
    MAX_PAGES = 4
    MAX_CHARS_PER_PAGE = 8000
    SCRAPE_TIMEOUT = 8
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    def __init__(self):
        self.bq_client = get_bigquery_client()
        self.openai_client = get_openai_client()
        self.apollo_key = _get_apollo_api_key()

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
            for field in ("llm_analysis_json", "social_links_json", "apollo_contacts_json"):
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
            for field in ("llm_analysis_json", "social_links_json", "apollo_contacts_json"):
                val = row.get(field)
                if isinstance(val, (dict, list)):
                    row[field] = json.dumps(val, ensure_ascii=False)
            self.bq_client.insert_rows_json(CACHE_TABLE, [row])
        except Exception as e:
            print(f"Intel cache save error: {e}")

    # ── Web Scraping ─────────────────────────────────────────

    def scrape_website(self, domain):
        if not domain:
            return ""
        base_url = f"https://{domain}"
        all_text = []
        visited = set()
        to_visit = [base_url]

        while to_visit and len(visited) < self.MAX_PAGES:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                resp = requests.get(url, headers=self.HEADERS, timeout=self.SCRAPE_TIMEOUT, allow_redirects=True)
                if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                    tag.decompose()

                page_text = soup.get_text(separator=" ", strip=True)
                page_text = re.sub(r"\s+", " ", page_text)[:self.MAX_CHARS_PER_PAGE]
                all_text.append(f"[PAGE: {url}]\n{page_text}")

                if len(visited) < self.MAX_PAGES:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("/"):
                            href = base_url + href
                        if domain in href and href not in visited:
                            lower = href.lower()
                            if any(kw in lower for kw in ["about", "propos", "equipe", "team", "service", "contact", "qui-sommes"]):
                                to_visit.insert(0, href)
            except Exception:
                continue

        return "\n\n".join(all_text)[:30000]

    # ── Social & Reputation Search ───────────────────────────

    def search_social_presence(self, name, city=""):
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
            (f'"{name}" {city} google avis', "google_business"),
        ]
        try:
            with DDGS() as ddgs:
                for query, category in searches:
                    try:
                        hits = list(ddgs.text(query, region="fr-fr", max_results=3))
                        for h in hits:
                            results[category].append({
                                "title": h.get("title", ""),
                                "url": h.get("href", ""),
                                "snippet": h.get("body", "")[:200]
                            })
                    except Exception:
                        continue
        except Exception as e:
            print(f"Social search error: {e}")
        return results

    def search_reputation(self, name):
        reviews_text = []
        queries = [
            f'"{name}" avis copropriété',
            f'"{name}" avis syndic',
        ]
        try:
            with DDGS() as ddgs:
                for query in queries:
                    try:
                        hits = list(ddgs.text(query, region="fr-fr", max_results=3))
                        for h in hits:
                            reviews_text.append(f"- {h.get('title', '')}: {h.get('body', '')[:300]}")
                    except Exception:
                        continue
        except Exception as e:
            print(f"Reputation search error: {e}")
        return "\n".join(reviews_text)[:5000]

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

        # 1. Find org by domain
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

        # 2. Fallback: find org by name
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

        # 3. Search all people (no title filter, broad search)
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
                         apollo_contacts=None, nb_copros=0, total_lots=0):
        if not self.openai_client:
            return self._fallback_analysis(social_links, legal_data, apollo_contacts)

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

        prompt = ANALYSIS_PROMPT.format(
            legal_data=json.dumps(legal_data, ensure_ascii=False, default=str) if legal_data else "Non disponible",
            website_content=website_content[:15000] if website_content else "Site web non accessible",
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
            return self._fallback_analysis(social_links, legal_data, apollo_contacts)

    def _fallback_analysis(self, social_links, legal_data, apollo_contacts=None):
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
        if legal_data:
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
            "contacts_cles": contacts_cles,
        }

    # ── Main Pipeline ────────────────────────────────────────

    def run_intelligence(self, siret, name, city="", domain=None, pappers_data=None,
                         nb_copros=0, total_lots=0, force_refresh=False):
        if not force_refresh:
            cached = self.get_cached_intel(siret)
            if cached:
                return cached

        website_content = self.scrape_website(domain)
        social_links = self.search_social_presence(name, city)
        reviews_data = self.search_reputation(name)
        apollo_contacts = self._fetch_apollo_contacts(domain, name)

        llm_analysis = self.analyze_with_llm(
            website_content=website_content,
            social_links=social_links,
            reviews_data=reviews_data,
            legal_data=pappers_data,
            apollo_contacts=apollo_contacts,
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
        }

        self.save_to_cache(result)
        return result
