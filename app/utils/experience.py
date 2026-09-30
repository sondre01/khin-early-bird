import re
from typing import Tuple, Dict, Any, Optional

# Keywords in job title that disqualify a fresh graduate with 0 experience
SENIOR_TITLE_PATTERNS = [
    r"\bsr\.?\b",
    r"\bsenior\b",
    r"\blead\b",
    r"\bprincipal\b",
    r"\barchitect\b",
    r"\bmanager\b",
    r"\bdirector\b",
    r"\bhead\s+of\b",
    r"\bhead\b",
    r"\bchief\b",
    r"\bstaff\s+engineer\b",
    r"\bsupervisor\b",
    r"\bmid[\s-]level\b",
    r"\bmidlevel\b",
    r"\bintermediate\b",
    r"\bexpert\b",
    r"\bspecialist\s*(?:2|ii|3|iii|iv|v)\b",
    r"\blevel\s*(?:2|ii|3|iii|iv|v)\b",
    r"\btier\s*(?:2|ii|3|iii|iv|v)\b",
    r"\bcoordinator\s*(?:3|iii|iv)\b",
    r"\bofficer\s*(?:2|ii|3|iii)\b"
]

# Keywords indicating explicitly fresh-grad or 0-experience friendly
FRESH_GRAD_FRIENDLY_PHRASES = [
    "fresh graduate", "fresh graduates", "fresh grad", "fresh grads",
    "open to fresh graduate", "open to fresh graduates",
    "fresh graduates are welcome", "fresh graduates welcome",
    "fresh graduates are encouraged", "fresh graduates encouraged",
    "accepting fresh graduates", "accepts fresh graduates",
    "no experience required", "no experience needed", "no prior experience",
    "0 experience", "zero experience", "0 years", "0-1 year", "0 to 1 year",
    "less than 1 year", "up to 1 year", "1 year or less",
    "entry level", "entry-level", "junior", "jr.", "jr ", "associate",
    "cadet", "trainee", "career starter", "beginner", "apprentice"
]

# Words to integer map for text numbers
WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
}

def is_fresh_grad_acceptable(title: str, description: str = "", job_type: str = "Regular") -> Tuple[bool, str, bool]:
    """
    Evaluates whether a job posting is acceptable for a candidate who is a
    fresh graduate with 0 full-time work experience (Khin Andrei Gamboa).
    
    Returns:
        (is_acceptable: bool, reason: str, is_explicit_fresh_grad: bool)
    """
    t_clean = re.sub(r'[_/\\-]', ' ', (title or "").lower().strip())
    d_clean = re.sub(r'[_/\\-]', ' ', (description or "").lower().strip())
    t_lower = (title or "").lower().strip()
    d_lower = (description or "").lower().strip()
    combined = f"{t_clean} {d_clean}"
    jt = (job_type or "Regular").capitalize()

    # Internships are inherently designed for students and fresh graduates
    if jt == "Internship" or any(w in t_clean for w in ["intern", "internship", "ojt", "practicum"]):
        return True, "Internship / OJT aligns with graduating student profile.", True

    # 1. Seniority Check in Title
    for pat in SENIOR_TITLE_PATTERNS:
        match = re.search(pat, t_clean)
        if match:
            matched_term = match.group(0)
            return False, f"Senior/Leadership title flagged ('{matched_term}'). Not suitable for 0 experience fresh graduate.", False

    # 2. Check for Explicit Fresh Graduate / 0 Experience Signals
    is_explicit_fresh_grad = any(phrase in combined for phrase in FRESH_GRAD_FRIENDLY_PHRASES)

    # 3. Disqualification: Explicit exclusionary phrases
    if any(phrase in combined for phrase in [
        "not open to fresh graduates",
        "not for fresh graduates",
        "no fresh graduates",
        "strictly requires experience",
        "strictly required prior experience"
    ]):
        return False, "Posting explicitly states it is not open to fresh graduates.", False

    # 4. Check for Demanded Years of Experience
    # Matches: "2+ years of experience", "minimum 3 years", "at least 2 yrs", "3-5 years"
    exp_patterns = [
        r"(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten))\+?\s*(?:to|-)\s*(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten))?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:work\s+|relevant\s+|professional\s+|industry\s+)?experience",
        r"(?:minimum|at\s+least|require[ds]?)\s+(?:of\s+)?(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten))\+?\s*(?:years?|yrs?)",
        r"(\d+|\b(?:one|two|three|four|five|six|seven|eight|nine|ten))\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:work\s+|relevant\s+|professional\s+|industry\s+)?experience\s+(?:is\s+)?required"
    ]

    found_years = []
    for pat in exp_patterns:
        matches = re.findall(pat, combined)
        for m in matches:
            val_str = m[0] if isinstance(m, tuple) else m
            if val_str:
                val_str = val_str.lower().strip()
                if val_str.isdigit():
                    found_years.append(int(val_str))
                elif val_str in WORD_TO_NUM:
                    found_years.append(WORD_TO_NUM[val_str])

    if found_years:
        max_exp = max(found_years)
        min_exp = min(found_years)

        # If 2+ years is required and there is no explicit fresh grad allowance:
        if min_exp >= 2 and not is_explicit_fresh_grad:
            return False, f"Demands {min_exp}+ years of experience. Khin is a fresh graduate with 0 work experience.", False

    # 5. Passed Verification
    if is_explicit_fresh_grad:
        return True, "Verified Fresh Graduate / 0 Experience friendly posting.", True

    # Neutral entry-level role (e.g., standard "Junior Developer", "Associate Engineer", or entry-tier title)
    return True, "Entry-level candidate profile suitable.", False
