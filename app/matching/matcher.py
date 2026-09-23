import re
from typing import List, Set
from app.job_sources.base import Job
from app.profile.models import CandidateProfile
from app.matching.models import MatchResult

class JobCandidateMatcher:
    """
    Explainable, deterministic matching engine.
    Compares a CandidateProfile against a Job.
    """
    
    # A dictionary for standardizing aliases (case-insensitive)
    ALIASES = {
        "ml": "machine learning",
        "ai": "artificial intelligence",
        "nlp": "natural language processing",
        "js": "javascript",
        "ts": "typescript",
        "aws": "amazon web services",
        "gcp": "google cloud",
        "reactjs": "react",
        "node.js": "nodejs",
        "vue.js": "vue",
        "k8s": "kubernetes"
    }

    # A static dictionary of common tech skills to identify what the job is asking for
    COMMON_TECH_SKILLS = {
        "python", "java", "c++", "c#", "javascript", "typescript", "go", "ruby", "rust",
        "react", "angular", "vue", "fastapi", "django", "flask", "spring", "express",
        "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "pinecone",
        "machine learning", "deep learning", "natural language processing", "computer vision", "llm", "genai",
        "pytorch", "tensorflow", "keras", "scikit-learn", "pandas", "numpy", "langchain",
        "amazon web services", "google cloud", "azure", "docker", "kubernetes", "ci/cd", "git", "linux",
        "agile", "scrum", "system design", "api design", "rest", "graphql"
    }

    def _normalize(self, term: str) -> str:
        """Normalizes a term by lowercasing, stripping, and resolving aliases."""
        term = term.lower().strip()
        return self.ALIASES.get(term, term)

    def _find_matches(self, candidate_items: List[str], text_pool: str) -> List[str]:
        """Finds which candidate items exist in the normalized text pool."""
        matches = []
        for item in candidate_items:
            norm_item = self._normalize(item)
            # Use regex boundaries to ensure we don't match 'go' inside 'google'
            pattern = r'\b' + re.escape(norm_item) + r'\b'
            if re.search(pattern, text_pool):
                matches.append(item)
        return matches

    def match(self, job: Job, candidate: CandidateProfile) -> MatchResult:
        # Create a normalized pool of all job text
        job_text = f"{job.title} {job.description}".lower()
        
        # Apply aliases to the job text to ensure e.g., "ML" becomes "machine learning" in the pool
        # This is a bit tricky with regex, so we'll just check both original and normalized versions.
        # Alternatively, simpler: just create a normalized set of words from the job.
        
        # We will iterate through all candidate items, check if their normalized form or original form is in the job text.
        # Let's improve the text pool by explicitly adding normalized forms of common words.
        expanded_job_text = job_text
        for alias, canonical in self.ALIASES.items():
            # If the alias is in the text as a whole word, append the canonical form to the text
            if re.search(r'\b' + re.escape(alias) + r'\b', job_text):
                expanded_job_text += f" {canonical}"
                
        # 1. Match specific categories
        matching_langs = self._find_matches(candidate.programming_languages, expanded_job_text)
        matching_frameworks = self._find_matches(candidate.frameworks, expanded_job_text)
        matching_ai = self._find_matches(candidate.ai_ml_technologies, expanded_job_text)
        matching_general_skills = self._find_matches(candidate.skills, expanded_job_text)
        
        # Deduplicate matched skills
        all_matched_skills_set = set()
        for lst in [matching_langs, matching_frameworks, matching_ai, matching_general_skills]:
            all_matched_skills_set.update(lst)
        matched_skills = sorted(list(all_matched_skills_set))
        
        # 2. Find missing skills
        # Extract all normalized candidate skills to a fast lookup set
        all_candidate_norm = set()
        for lst in [candidate.skills, candidate.programming_languages, candidate.frameworks, candidate.databases, candidate.ai_ml_technologies]:
            for item in lst:
                all_candidate_norm.add(self._normalize(item))
                
        missing_skills = []
        for skill in self.COMMON_TECH_SKILLS:
            # If the job requires it
            if re.search(r'\b' + re.escape(skill) + r'\b', expanded_job_text):
                # But the candidate doesn't have it
                if skill not in all_candidate_norm:
                    missing_skills.append(skill)
                    
        missing_skills = sorted(list(set(missing_skills)))
        
        # 3. Location Match
        location_match = "Unknown"
        job_loc = job.location.lower()
        if not job_loc or job_loc == "not specified":
            location_match = "Unknown"
        else:
            location_match = "Not Matched"
            for pref_loc in candidate.preferred_locations:
                pref_norm = pref_loc.lower().strip()
                if pref_norm in job_loc or job_loc in pref_norm or "remote" in job_loc and pref_norm == "remote":
                    location_match = "Matched"
                    break
                    
        # 4. Experience Match (Basic heuristic)
        exp_match = "Unknown"
        job_exp = job.experience.lower()
        cand_exp = candidate.experience_level.lower()
        if not job_exp or job_exp == "not specified":
            exp_match = "Unknown"
        else:
            # Very simple heuristic: if job asks for senior and candidate is senior
            if "senior" in job_exp and "senior" in cand_exp:
                exp_match = "Matched"
            elif "junior" in job_exp and "junior" in cand_exp:
                exp_match = "Matched"
            elif "fresher" in job_exp and "fresher" in cand_exp:
                exp_match = "Matched"
            else:
                # Fallback to string matching
                if cand_exp in job_exp or job_exp in cand_exp:
                    exp_match = "Matched"
                else:
                    exp_match = "Not Matched"
                    
        # 5. Education Match (Basic heuristic)
        edu_match = "Unknown"
        cand_edu = candidate.education.lower()
        if "bachelor" in expanded_job_text or "b.s" in expanded_job_text or "degree" in expanded_job_text:
            if "bachelor" in cand_edu or "b.s" in cand_edu or "degree" in cand_edu:
                edu_match = "Matched"
            else:
                edu_match = "Not Matched"
                
        # 6. Generate Explanation
        explanation = f"Matched {len(matched_skills)} core skills and found {len(missing_skills)} potential missing skills. "
        if location_match == "Matched":
            explanation += "Location aligns with candidate preferences."
        elif location_match == "Not Matched":
            explanation += "Location does not align with candidate preferences."

        return MatchResult(
            matched_skills=matched_skills,
            missing_skills=missing_skills,
            matching_programming_languages=matching_langs,
            matching_frameworks=matching_frameworks,
            matching_ai_ml_technologies=matching_ai,
            location_match=location_match,
            experience_match=exp_match,
            education_match=edu_match,
            explanation=explanation
        )
