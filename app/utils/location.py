from typing import Optional

NCR_KEYWORDS = [
    "national capital region", "ncr", "metro manila",
    "manila", "pasig", "makati", "taguig", "bgc", "bonifacio global city",
    "quezon city", "qc", "mandaluyong", "pasay", "parañaque", "paranaque",
    "muntinlupa", "alabang", "las piñas", "las pinas", "marikina",
    "valenzuela", "malabon", "navotas", "caloocan", "san juan", "pateros",
    "ortigas", "eastwood"
]

def is_ncr_location(location: Optional[str], work_type: Optional[str] = "") -> bool:
    """
    Returns True if the job location is located within Metro Manila / NCR
    or is Remote / Work-from-Home (which is workable from NCR).
    """
    loc = (location or "").lower()
    wt = (work_type or "").lower()
    
    # Remote roles are workable by an NCR-based candidate
    if "remote" in wt or "remote" in loc or "work from home" in loc or "wfh" in loc:
        return True
        
    return any(k in loc for k in NCR_KEYWORDS)
