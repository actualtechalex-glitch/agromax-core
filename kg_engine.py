import os
import numpy as np
from lightrag import LightRAG
from lightrag.utils import EmbeddingFunc

# Заглушка для векторизатора (пока мы не подключим реальную нейросеть)
async def mock_embedding_func(texts: list[str]) -> np.ndarray:
    # Генерируем случайные векторы (размерность 384 — стандарт для быстрых моделей)
    return np.random.rand(len(texts), 384)

class AgromaxKnowledgeGraph:
    def __init__(self, workspace_dir="/root/agromax_infinity/knowledge_graph_db/"):
        self.workspace_dir = workspace_dir
        
        print(f"Инициализация базы знаний АГРОМАКС в директории: {self.workspace_dir}")
        
        try:
            self.rag = LightRAG(
                working_dir=self.workspace_dir,
                # Заглушка для LLM
                llm_model_func=lambda *args, **kwargs: "Mock LLM Response", 
                # Наш новый фейковый векторизатор для успешного старта
                embedding_func=EmbeddingFunc(
                    embedding_dim=384,
                    max_token_size=8192,
                    func=mock_embedding_func
                )
            )
            print("Движок LightRAG успешно смонтирован!")
        except Exception as e:
            print(f"Ошибка при монтировании базы: {e}")

    def status(self):
        if os.path.exists(self.workspace_dir):
            files = os.listdir(self.workspace_dir)
            print(f"Файлы в хранилище графа: {files}")

if __name__ == "__main__":
    kg = AgromaxKnowledgeGraph()
    kg.status()
