"""
資料庫模型
"""
from app.models.scam_knowledge_base import ScamKnowledgeBase
from app.models.task import Task
from app.models.admin_override import AdminOverride
from app.models.user_feedback import UserFeedback

__all__ = [
    "ScamKnowledgeBase",
    "Task",
    "AdminOverride",
    "UserFeedback",
]

