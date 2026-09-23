from app.profile.models import CandidateProfile, Project

# A safe, mock placeholder profile for development/testing
# Keeps sensitive information out of source code.
MOCK_CANDIDATE = CandidateProfile(
    name="Jane Doe",
    experience_level="Mid-Level (3 Years)",
    education="B.S. Computer Science",
    target_roles=["AI Engineer", "Backend Developer", "GenAI Developer"],
    preferred_locations=["Remote", "Berlin", "Chennai"],
    skills=["System Design", "Agile Development", "API Design"],
    programming_languages=["Python", "JavaScript", "Go"],
    frameworks=["FastAPI", "React", "LangChain"],
    databases=["PostgreSQL", "MongoDB", "Pinecone"],
    ai_ml_technologies=["PyTorch", "OpenAI API", "Hugging Face"],
    projects=[
        Project(
            name="Autonomous Agent",
            description="Built a specialized AI assistant that parses documents.",
            technologies=["Python", "LangChain", "OpenAI API"],
            url="https://github.com/janedoe/agent"
        ),
        Project(
            name="E-Commerce API",
            description="Scalable backend for a retail platform.",
            technologies=["Python", "FastAPI", "PostgreSQL"]
        )
    ]
)
