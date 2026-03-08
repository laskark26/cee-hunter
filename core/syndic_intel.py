
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
ANALYSIS_VERSION = 6
DEFAULT_TTL_DAYS = 30

# ── SerpApi Configuration ─────────────────────────────────
SERPAPI_KEY = st.secrets.get("SERPAPI_KEY", os.environ.get("SERPAPI_KEY", ""))
SERPAPI_BASE_URL = "https://serpapi.com/search.json"

URL_BLACKLIST = [
    "pagesjaunes.fr", "societe.com", "linkedin.com", "facebook.com",
    "verif.com", "meilleursyndic.com", "yelp.fr", "google.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com",
    "annuaire-entreprises.data.gouv.fr", "pappers.fr", "infogreffe.fr",
    "manageo.fr", "score3.fr", "entreprise.lefigaro.fr",
    "syndicompare.com", "syndic-one.com", "cotoit.com", "comparateur-syndic.com",
    "changersyndic.net", "monimmeuble.com", "baticopro.com",
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
    "conseiller", "collaborateur", "annuaire", "direction", "gerant", "agence",
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

## Contacts extraits du site web (scraper LLM)
{scraped_contacts}

## Contexte
Ce syndic gère {nb_copros} copropriétés représentant {total_lots} lots au total.
Nous cherchons à le prospecter pour des projets de rénovation énergétique (CEE - Certificats d'Économies d'Énergie).

## Instructions
1. Croise les données de toutes les sources pour vérifier la cohérence (téléphone, adresse, email).
2. Privilégie les données Google Maps et du site web pour le téléphone et l'email (plus fiables que Pappers).
3. Fusionne les contacts Apollo et les contacts extraits du site web dans `contacts_cles`. Déduplique par nom/email. Privilégie les rôles de direction, gestion de copropriété et administration de biens.
4. Produis UNIQUEMENT un JSON valide (sans markdown, sans ```), avec cette structure exacte :
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
            "scraped_contacts_json": "STRING",
        }
        for col, col_type in new_cols.items():
            if col not in existing_cols:
                alter_query = f"ALTER TABLE `{CACHE_TABLE}` ADD COLUMN {col} {col_type}"
                client.query(alter_query).result()
                print(f"Migration: Added column {col}")
    except Exception as e:
        print(f"Error creating/migrating intel cache: {e}")


class SyndicIntelligence:
    MAX_PAGES = 8
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
        self.serpapi_key = SERPAPI_KEY

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
                          "scraped_phones", "scraped_emails", "google_maps_json", "serp_results_json",
                          "scraped_contacts_json"):
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
                          "scraped_phones", "scraped_emails", "google_maps_json", "serp_results_json",
                          "scraped_contacts_json"):
                val = row.get(field)
                if isinstance(val, (dict, list)):
                    row[field] = json.dumps(val, ensure_ascii=False)
            self.bq_client.insert_rows_json(CACHE_TABLE, [row])
        except Exception as e:
            print(f"Intel cache save error: {e}")

    # ── SerpApi: Google SERP Search ─────────────────────────

    def _serp_search(self, query_str, num_results=5):
        """Single Google SERP search via SerpApi. Returns list of organic results."""
        if not self.serpapi_key:
            print("DEBUG: SerpApi key missing, skipping SERP search")
            return []
        try:
            params = {
                "engine": "google",
                "api_key": self.serpapi_key,
                "q": query_str,
                "google_domain": "google.fr",
                "gl": "fr",
                "hl": "fr",
                "num": str(num_results),
            }
            resp = requests.get(SERPAPI_BASE_URL, params=params, timeout=60)
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

    # ── SerpApi: Google Maps Search ─────────────────────────

    def google_maps_search(self, name, city="", lat=None, lon=None):
        """Search Google Maps for the syndic via SerpApi and return structured data."""
        if not self.serpapi_key:
            print("DEBUG: SerpApi key missing, skipping Maps search")
            return None
        latitude = lat or 48.8566
        longitude = lon or 2.3522
        query_str = f"{name} {city}".strip() if city else name

        try:
            params = {
                "engine": "google_maps",
                "api_key": self.serpapi_key,
                "q": query_str,
                "ll": f"@{latitude},{longitude},14z",
                "hl": "fr",
                "type": "search",
            }
            resp = requests.get(SERPAPI_BASE_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("local_results", [])
                if not results:
                    print(f"DEBUG: Google Maps returned 0 results for '{query_str}'")
                    return None

                best = self._find_best_maps_match(results, name)
                if best:
                    return {
                        "name": best.get("title", ""),
                        "address": best.get("address", ""),
                        "stars": best.get("rating"),
                        "ratings": best.get("reviews"),
                        "phone": best.get("phone", ""),
                        "url": best.get("website", ""),
                        "type": best.get("types", best.get("type", [])),
                        "open": best.get("operating_hours", {}),
                        "place_id": best.get("place_id", ""),
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
            r_name = re.sub(r'[^a-zA-Z0-9\s]', '', (r.get("title") or "").lower())
            score = fuzz.partial_ratio(clean_name, r_name)
            if score > best_score:
                best_score = score
                best_result = r
        if best_score >= 50:
            return best_result
        return results[0] if results else None

    # ── Web Scraping (BeautifulSoup direct) ─────────────────

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
        """Scrape a single page directly with requests + BeautifulSoup."""
        return requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }, timeout=self.SCRAPE_TIMEOUT, allow_redirects=True)

    def scrape_website(self, domain):
        """Scrape the syndic website using direct requests + BeautifulSoup.
        Returns (content, phones, emails, team_pages_text).
        team_pages_text is a list of texts from priority pages (equipe/contact/etc.)
        """
        if not domain:
            return "", [], [], []
        base_url = f"https://{domain}"
        all_text = []
        all_phones = set()
        all_emails = set()
        team_pages_text = []
        visited = set()
        to_visit = [base_url]
        page_count = 0

        while to_visit and len(visited) < self.MAX_PAGES:
            url = to_visit.pop(0)
            if url in visited:
                continue
            if not self._is_useful_page(url):
                continue
            visited.add(url)
            try:
                resp = self._scrape_single_page(url)
                final_url = resp.url
                if resp.status_code != 200 or "text/html" not in resp.headers.get("Content-Type", ""):
                    continue
                visited.add(final_url)
                soup = BeautifulSoup(resp.text, "html.parser")
                page_count += 1

                page_phones, page_emails = self._extract_contact_info(soup)
                all_phones.update(page_phones)
                all_emails.update(page_emails)

                if len(visited) < self.MAX_PAGES:
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("javascript:") or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
                            continue
                        if href.startswith("/"):
                            href = base_url + href
                        elif not href.startswith("http"):
                            href = base_url + "/" + href
                        if domain in href and href not in visited and self._is_useful_page(href):
                            if self._is_priority_page(href):
                                to_visit.insert(0, href)
                            elif len(to_visit) < 15:
                                to_visit.append(href)

                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
                    tag.decompose()

                page_text = soup.get_text(separator=" ", strip=True)
                page_text = re.sub(r"\s+", " ", page_text)[:self.MAX_CHARS_PER_PAGE]
                all_text.append(f"[PAGE: {final_url}]\n{page_text}")

                is_home = page_count == 1
                is_priority = self._is_priority_page(final_url)
                if is_priority or is_home:
                    team_pages_text.append(f"[PAGE: {final_url}]\n{page_text}")
                    print(f"DEBUG: Team page detected: {final_url} (home={is_home}, priority={is_priority})")
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

        return content, list(all_phones), list(all_emails), team_pages_text

    # ── LLM Contact Extraction ─────────────────────────────

    def _extract_contacts_with_llm(self, team_pages_text):
        """Use GPT-4o-mini to extract structured contacts from team/contact page text."""
        if not self.openai_client or not team_pages_text:
            return []

        combined = "\n\n".join(team_pages_text)[:16000]

        system_prompt = (
            "Tu es un enquêteur commercial d'élite spécialisé dans le secteur immobilier français. "
            "Ton rôle : identifier les décideurs et contacts clés au sein des syndics de copropriété "
            "pour permettre une prospection B2B ciblée sur les projets de rénovation énergétique (CEE).\n\n"
            "Tu travailles pour une entreprise qui aide les copropriétés à réaliser des travaux de "
            "rénovation énergétique financés par les Certificats d'Économies d'Énergie. "
            "Pour cela, tu dois identifier les personnes qui prennent les décisions au sein des syndics : "
            "les gérants, directeurs, responsables syndic et gestionnaires de copropriété.\n\n"
            "Tu es méticuleux, tu ne rates aucun nom, aucun numéro, aucun email. "
            "Tu lis entre les lignes : un 'Contactez Nicolas au 03...' est un contact à extraire. "
            "Un 'dirigé par M. Dupont depuis 20 ans' est un contact à extraire. "
            "Tu réponds UNIQUEMENT en JSON valide, sans markdown."
        )

        prompt = (
            "## Objectif\n\n"
            "Analyse le texte ci-dessous extrait du site web d'un syndic de copropriété. "
            "Ton objectif est d'identifier TOUTES les personnes nommées et de reconstituer leur fiche contact "
            "la plus complète possible (nom, poste, téléphone, email).\n\n"
            "## Texte extrait du site web\n\n"
            f"{combined}\n\n"
            "## Où chercher les contacts\n\n"
            "Sois exhaustif. Les contacts se cachent partout :\n"
            "- **Pages équipe/conseillers** : fiches avec nom, poste, téléphone, email\n"
            "- **Pages syndic/copropriété** : 'Contactez X au...', 'votre interlocuteur', 'responsable syndic'\n"
            "- **Page d'accueil** : 'dirigé par...', 'fondé par...', 'son directeur X'\n"
            "- **Mentions légales** : 'directeur de publication : M./Mme X', 'gérant : X'\n"
            "- **Formulaires de contact** : 'joindre X au...', 'contacter X par email à...'\n"
            "- **Signatures et pieds de page** : noms associés à des numéros directs\n\n"
            "## Hiérarchie des contacts (du plus important au moins important)\n\n"
            "1. **Direction** : Gérant, PDG, Président, Directeur général, Fondateur\n"
            "2. **Responsables syndic** : Directeur syndic, Responsable copropriété, Principal de copropriété\n"
            "3. **Gestionnaires** : Gestionnaire de copropriété, Administrateur de biens\n"
            "4. **Opérationnels** : Chargé de clientèle, Conseiller, Négociateur, Agent commercial\n"
            "5. **Support** : Comptable syndic, Assistant(e), Gestionnaire locatif\n\n"
            "## Règles d'extraction\n\n"
            "- Extrais CHAQUE personne nommée, même si tu n'as qu'un nom sans téléphone ni email\n"
            "- Si un téléphone ou email apparaît à proximité d'un nom (même quelques lignes avant/après), associe-le\n"
            "- Déduis le poste à partir du contexte si non explicitement indiqué (ex: 'dirigé par X' → poste: 'Dirigeant')\n"
            "- Normalise les noms en 'Prénom Nom' (majuscule initiale)\n"
            "- Normalise les téléphones au format français (ex: 03 88 39 20 39 ou 06 82 59 65 43)\n"
            "- Ne confonds pas le standard téléphonique général avec un numéro direct personnel\n\n"
            "## Format de sortie\n\n"
            "Réponds UNIQUEMENT en JSON valide (sans markdown, sans ```), sous forme de liste :\n"
            '[{"nom": "Prénom Nom", "poste": "Titre du poste", "email": "", "telephone": "", "source": "site_web"}]\n\n'
            "Si aucun contact n'est identifiable, retourne []."
        )

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=3000,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            contacts = json.loads(raw)
            if isinstance(contacts, list):
                print(f"DEBUG: LLM extracted {len(contacts)} contacts from team pages")
                return contacts
        except Exception as e:
            print(f"DEBUG: LLM contact extraction error: {e}")
        return []

    # ── SerpApi: Social & Reputation (via Google SERP) ──────

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
            domain_clean = re.sub(r'[^a-zA-Z0-9]', '', domain_name.lower())
            score = fuzz.partial_ratio(clean_name, domain_clean)
            source_bonus = {"pappers": 15, "google_maps": 12, "pappers_email": 8, "serp": 0}.get(source, 0)
            total = score + source_bonus
            if total > best_score:
                best_score = total
                best_domain = domain
                best_source = source

        if best_score >= 45:
            return best_domain, best_source

        # Fallback: trust Google Maps URL if available (very reliable source)
        for source, domain in candidates:
            if source == "google_maps":
                print(f"DEBUG: Domain fallback to Google Maps: {domain} (best fuzzy score was {best_score})")
                return domain, "google_maps_fallback"

        # Fallback: take the most common SERP domain
        serp_domains = [d for s, d in candidates if s == "serp"]
        if serp_domains:
            from collections import Counter
            most_common = Counter(serp_domains).most_common(1)[0]
            if most_common[1] >= 2:
                print(f"DEBUG: Domain fallback to most common SERP domain: {most_common[0]} (appeared {most_common[1]}x)")
                return most_common[0], "serp_fallback"

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
                         apollo_contacts=None, google_maps_data=None, nb_copros=0, total_lots=0,
                         scraped_contacts=None):
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

        scraped_contacts_summary = "Aucun contact extrait du site web"
        if scraped_contacts:
            lines_sc = []
            for sc in scraped_contacts[:20]:
                parts_sc = [f"{sc.get('nom', 'N/A')} - {sc.get('poste', 'N/A')}"]
                if sc.get("email"):
                    parts_sc.append(f"Email: {sc['email']}")
                if sc.get("telephone"):
                    parts_sc.append(f"Tél: {sc['telephone']}")
                lines_sc.append(" | ".join(parts_sc))
            scraped_contacts_summary = "\n".join(lines_sc)

        prompt = ANALYSIS_PROMPT.format(
            legal_data=json.dumps(legal_data, ensure_ascii=False, default=str) if legal_data else "Non disponible",
            website_content=website_content[:15000] if website_content else "Site web non accessible",
            google_maps_data=maps_summary,
            social_links=json.dumps(social_links, ensure_ascii=False) if social_links else "Aucun réseau social trouvé",
            reviews_data=reviews_data if reviews_data else "Aucun avis trouvé",
            apollo_contacts=contacts_summary,
            scraped_contacts=scraped_contacts_summary,
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
                         nb_copros=0, total_lots=0, force_refresh=False, lat=None, lon=None,
                         status_callback=None):
        def _status(msg):
            print(f"DEBUG: {msg}")
            if status_callback:
                status_callback(msg)

        if not force_refresh:
            cached = self.get_cached_intel(siret)
            if cached:
                return cached

        # 1. Google SERP
        _status(f"[1/7] Recherche Google SERP pour '{name}'...")
        serp_results = self.google_search(name)
        _status(f"[1/7] SERP : {len(serp_results)} résultats trouvés")

        # 2. Google Maps
        _status(f"[2/7] Recherche Google Maps pour '{name}' à '{city}'...")
        maps_data = self.google_maps_search(name, city, lat=lat, lon=lon)
        if maps_data:
            _status(f"[2/7] Maps : {maps_data.get('name', '?')} — {maps_data.get('stars', '?')}/5 ({maps_data.get('ratings', 0)} avis)")
        else:
            _status("[2/7] Maps : aucun résultat")

        # 3. Identify domain
        _status(f"[3/7] Identification du domaine (fourni: {domain or 'aucun'})...")
        if not domain:
            domain, domain_source = self.identify_domain(serp_results, name, pappers_data, maps_data)
            _status(f"[3/7] Domaine identifié : {domain or 'aucun'} (source: {domain_source})")
        else:
            domain_source = "provided"
            _status(f"[3/7] Domaine fourni : {domain}")

        # 4. Scrape website
        _status(f"[4/7] Scraping du site {domain or 'N/A'}...")
        website_content, scraped_phones, scraped_emails, team_pages_text = self.scrape_website(domain)
        _status(f"[4/7] Scraping : {len(website_content)} chars, {len(scraped_phones)} tél, {len(scraped_emails)} emails, {len(team_pages_text)} pages équipe")

        # 4b. LLM contact extraction from team pages
        scraped_contacts = []
        if team_pages_text:
            _status(f"[4b] Extraction LLM de contacts depuis {len(team_pages_text)} pages équipe/contact...")
            scraped_contacts = self._extract_contacts_with_llm(team_pages_text)
            _status(f"[4b] {len(scraped_contacts)} contacts extraits par LLM")
        else:
            _status("[4b] Aucune page équipe/contact détectée, extraction LLM ignorée")

        # 5. Social presence
        _status("[5/7] Recherche présence réseaux sociaux...")
        social_links = self.search_social_presence(name, city)
        social_count = sum(len(v) for v in social_links.values() if isinstance(v, list))
        _status(f"[5/7] Réseaux sociaux : {social_count} liens trouvés")

        # 6. Reputation
        _status("[6/7] Recherche réputation en ligne...")
        reviews_data = self.search_reputation(name)
        _status(f"[6/7] Réputation : {len(reviews_data)} chars collectés")

        # 7. Apollo contacts
        _status("[7/7] Recherche contacts Apollo...")
        apollo_contacts = self._fetch_apollo_contacts(domain, name)
        _status(f"[7/7] Apollo : {len(apollo_contacts)} contacts trouvés")

        # LLM Analysis
        if domain:
            _status(f"🌐 Site identifié : {domain}")
        _status("Analyse LLM en cours (GPT-4o-mini)...")
        llm_analysis = self.analyze_with_llm(
            website_content=website_content,
            social_links=social_links,
            reviews_data=reviews_data,
            legal_data=pappers_data,
            apollo_contacts=apollo_contacts,
            google_maps_data=maps_data,
            nb_copros=nb_copros,
            total_lots=total_lots,
            scraped_contacts=scraped_contacts,
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
            "scraped_contacts_json": scraped_contacts,
        }

        self.save_to_cache(result)
        return result
