"""
What one skill name implies about another.

Two relations, kept apart on purpose.

IS_A says a thing the person has genuinely satisfies a broader requirement:
PostgreSQL is a SQL database, GitHub Actions is CI/CD. Matching on whole words
alone missed these, so a posting asking for "relational databases and SQL" read
as unbacked against a bullet about designing a PostgreSQL schema.

SIBLINGS says two things sit in the same category. They are never a substitute
for each other. Zustand is not Redux and AWS is not Azure, and a CV that claims
otherwise fails the interview. Siblings only annotate a gap, so the person is
told "they want Redux, you have Zustand" rather than being told nothing, or
worse, being told it is covered.
"""

import re

# A term the person has -> the broader terms it honestly satisfies.
IS_A: dict[str, set[str]] = {
    "postgresql": {"sql", "relational", "database", "rdbms", "postgres"},
    "postgres": {"sql", "relational", "database", "rdbms"},
    "mysql": {"sql", "relational", "database", "rdbms"},
    "sqlite": {"sql", "relational", "database"},
    "mongodb": {"nosql", "database"},
    "prisma": {"orm", "database"},
    "github actions": {"ci", "cd", "cicd", "pipeline", "automation"},
    "gitlab ci": {"ci", "cd", "cicd", "pipeline"},
    "jenkins": {"ci", "cd", "cicd", "pipeline"},
    "jest": {"testing", "test", "unit"},
    "vitest": {"testing", "test", "unit"},
    "mocha": {"testing", "test", "unit"},
    "playwright": {"testing", "test", "e2e", "integration"},
    "cypress": {"testing", "test", "e2e", "integration"},
    "detox": {"testing", "test", "e2e"},
    "pytest": {"testing", "test", "unit"},
    "aws lambda": {"aws", "cloud", "serverless"},
    "aws cdk": {"aws", "cloud", "infrastructure"},
    "eventbridge": {"aws", "cloud"},
    "azure": {"cloud"},
    "gcp": {"cloud"},
    "google cloud": {"cloud"},
    "supabase": {"backend", "database", "postgres"},
    "cloudflare": {"cdn", "dns"},
    "docker": {"container", "containerisation", "containerization"},
    "kubernetes": {"container", "orchestration"},
    "git": {"version control", "source control"},
    "github": {"version control", "source control", "git"},
    "react native": {"mobile", "ios", "android", "cross-platform"},
    "expo": {"mobile", "ios", "android", "react native"},
    "swift": {"ios", "mobile"},
    "kotlin": {"android", "mobile"},
    "next.js": {"react", "ssr", "server-side", "fullstack", "full-stack"},
    "nuxt": {"vue", "ssr", "server-side"},
    "nestjs": {"node.js", "node", "backend", "api", "server"},
    "express": {"node.js", "node", "backend", "api", "server"},
    "fastapi": {"python", "backend", "api", "server"},
    "django": {"python", "backend", "api", "server"},
    "flask": {"python", "backend", "api"},
    "asp.net": {"c#", "backend", "api", ".net"},
    "entity framework": {"c#", "orm", ".net"},
    "typescript": {"javascript", "js"},
    "rest": {"api"},
    "graphql": {"api"},
    "tailwind": {"css", "styling"},
    "sass": {"css", "styling"},
    "styled-components": {"css", "styling"},
    "jwt": {"authentication", "auth"},
    "auth0": {"authentication", "auth", "oauth", "sso"},
    "figma": {"design"},
    # A posting says "point of sale" or "ecommerce"; a bullet says "payment
    # gateway" or "checkout". Same work, no shared word.
    "payment": {"ecommerce", "e-commerce", "pos", "point of sale", "checkout", "billing", "commerce"},
    "payments": {"ecommerce", "e-commerce", "pos", "point of sale", "checkout", "billing"},
    "checkout": {"ecommerce", "payment", "pos", "point of sale"},
    "invoice": {"billing", "payment", "ecommerce"},
    "invoicing": {"billing", "payment", "ecommerce"},
    "stripe": {"payment", "ecommerce", "checkout"},
    "finix": {"payment", "ecommerce", "checkout"},
    # Written as one word in a skills list, as two in a posting.
    "frontend": {"front end", "ui", "client-side", "client"},
    "front-end": {"frontend", "ui", "client-side"},
    "backend": {"back end", "server-side", "server", "api"},
    "back-end": {"backend", "server-side", "server", "api"},
    "fullstack": {"full stack", "frontend", "backend", "front end", "back end"},
    "full-stack": {"fullstack", "frontend", "backend", "front end", "back end"},
    "claude api": {"ai", "llm", "genai", "artificial", "intelligence"},
    "openai": {"ai", "llm", "genai", "artificial", "intelligence"},
    "langchain": {"ai", "llm", "genai"},
    "agile": {"scrum", "backlog", "sprint", "planning", "estimation", "standup"},
    "scrum": {"agile", "backlog", "sprint", "planning"},
    "storybook": {"design system", "component library", "documentation"},
}

# Same category, never a substitute. Used only to explain a gap.
SIBLINGS: dict[str, set[str]] = {
    "state management": {
        "redux", "zustand", "jotai", "mobx", "recoil", "context api", "pinia",
        "vuex", "ngrx", "redux toolkit",
    },
    "cloud provider": {"aws", "azure", "gcp", "google cloud", "digitalocean", "heroku"},
    "testing framework": {
        "jest", "vitest", "mocha", "jasmine", "cypress", "playwright", "detox",
        "pytest", "junit", "rspec",
    },
    "database": {
        "postgresql", "postgres", "mysql", "mongodb", "sqlite", "oracle",
        "sql server", "dynamodb", "redis", "cassandra",
    },
    "styling": {
        "tailwind", "css", "sass", "scss", "styled-components", "emotion",
        "less", "bootstrap", "material ui", "chakra",
    },
    "front-end framework": {"react", "vue", "angular", "svelte", "solid", "ember"},
    "back-end framework": {
        "nestjs", "express", "django", "flask", "fastapi", "rails", "laravel",
        "spring", "asp.net", "koa", "hapi",
    },
    "language": {
        "typescript", "javascript", "python", "c#", "java", "go", "ruby", "php",
        "rust", "kotlin", "swift", "scala",
    },
    "mobile framework": {"react native", "flutter", "expo", "ionic", "xamarin"},
    "orm": {"prisma", "typeorm", "sequelize", "entity framework", "sqlalchemy", "hibernate"},
}


def implied(terms: set[str], names: list[str]) -> set[str]:
    """`terms` plus everything the person's own skill names honestly imply.

    Matched on the full skill name as written, not on single words, so
    "AWS Lambda" implies cloud while a stray "lambda" in a bullet does not.
    """
    extra: set[str] = set()
    for name in names:
        # Punctuation to spaces first: "TypeScript." and "TypeScript," were
        # not matching, which is every bullet, since every bullet ends in one.
        lowered = re.sub(r"[.,;:()\"']", " ", name.casefold()).strip()
        for key, broader in IS_A.items():
            if key == lowered or key in lowered.split(" / ") or f" {key} " in f" {lowered} ":
                extra |= broader
    # Split the way _terms does, or "full-stack" never meets "full stack". A
    # phrase stays one item though: split to words, "cross-platform" answered
    # "cloud platform" and "source control" answered "open source".
    out = set(terms)
    for phrase in extra:
        words = [_singular(w) for w in re.split(r"[-\u2010-\u2015/\s]+", phrase) if w]
        out.add(words[0] if len(words) == 1 else " ".join(w for w in words if len(w) > 2))
    return out


def _singular(word: str) -> str:
    """The same rule as generate._terms, so both sides of a match agree. rstrip("s") made "cross" into "cro"."""
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def backs(wants: set[str], evidence: set[str]) -> bool:
    """A word of evidence answers when it is among the wants; a phrase, only when all of it is."""
    return any(set(item.split()) <= wants for item in evidence)


def category_of(name: str) -> tuple[str, set[str]] | None:
    """The category a requirement falls in, and its members, or None."""
    lowered = name.strip().casefold()
    for category, members in SIBLINGS.items():
        if any(m == lowered or f" {m} " in f" {lowered} " for m in members):
            return category, members
    return None
