from pydantic import BaseModel

class AnalyzeRequest(BaseModel):
    user_id: str = "my_user"
    text: str

class SaveItemRequest(BaseModel):
    user_id: str = "my_user"
    item_type: str
    term: str
    lemma: str
    context_sentence: str
    status: str = "learning"
    translation: str = ""
    breakdown: str = ""

class ExplainRequest(BaseModel):
    text: str
    lemma: str = ""
    sentence: str = ""
    mode: str = "translate"  # "translate" | "breakdown"