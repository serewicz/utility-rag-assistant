"""Role-based access control.

Each document carries one label. Each role may read a set of labels.
The filter is applied INSIDE the retrieval query, before ranking, so a
restricted chunk can never reach the model's context window.
"""
ROLE_LABELS: dict[str, set[str]] = {
    "public": {"public"},
    "field-tech": {"public", "field-tech"},
    "cip-analyst": {"public", "field-tech", "cip-restricted"},
}

# Demo users. In production, map these from your identity provider (SSO groups).
USERS: dict[str, str] = {
    "guest": "public",
    "maria": "field-tech",
    "dev": "cip-analyst",
    "tim": "cip-analyst",
}


def labels_for(user: str) -> tuple[str, set[str]]:
    role = USERS.get(user, "public")  # unknown users get the least access
    return role, ROLE_LABELS[role]
