"""
核心检索模块
实现两阶段检索：向量粗排 + Reranker 精排重排
"""

from typing import List, Dict

from sentence_transformers import CrossEncoder
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from core.config import settings


class AdvancedRetriever:
    """
    高级检索器
    实现两阶段检索：向量粗排 + Reranker 精排重排
    """
    
    # 类级别单例：CrossEncoder 模型
    # 避免重复加载模型，提高性能
    _reranker_model = None
    
    def __init__(self):
        """
        初始化高级检索器
        连接 Chroma 向量库并加载 Reranker 模型
        """
        # Chroma 数据库目录
        self.chroma_dir = "./data/chroma_db"
        
        # 初始化 Embedding 模型（用于连接 Chroma）
        self.embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # 连接到已存在的 Chroma 向量库
        self.vectorstore = Chroma(
            persist_directory=self.chroma_dir,
            embedding_function=self.embeddings,
            collection_name="rag_documents"
        )
        
        # 加载 Reranker 模型（单例模式）
        # 使用 BAAI/bge-reranker-base 进行精细重排
        if AdvancedRetriever._reranker_model is None:
            AdvancedRetriever._reranker_model = CrossEncoder(
                'BAAI/bge-reranker-base',
                max_length=512,
                device='cpu'
            )
        
        self.reranker = AdvancedRetriever._reranker_model
    
    def retrieve_and_rerank(self, query: str) -> List[Dict[str, any]]:
        """
        两阶段检索：向量粗排 + Reranker 精排重排
        
        Args:
            query: 用户查询问题
            
        Returns:
            List[Dict]: 包含 content 和 score 的字典列表
                - content: 文档片段内容
                - score: Reranker 计算的相关性得分
                
        Raises:
            Exception: 检索失败
        """
        try:
            # 第一阶段：向量粗排
            # 使用 Chroma 的 similarity_search 获取 Top-K 个文档片段
            # K 由配置中的 TOP_K_RETRIEVAL 决定（默认 10）
            retrieved_docs = self.vectorstore.similarity_search(
                query=query,
                k=settings.TOP_K_RETRIEVAL
            )
            
            if not retrieved_docs:
                return []
            
            # 第二阶段：Reranker 精排重排
            # 组装 (query, doc) 对，用于 Reranker 打分
            query_doc_pairs = [(query, doc.page_content) for doc in retrieved_docs]
            
            # 使用 CrossEncoder 的 predict 方法计算相关性得分
            scores = self.reranker.predict(query_doc_pairs)
            
            # 将文档和得分组合，并按得分降序排序
            doc_score_pairs = list(zip(retrieved_docs, scores))
            doc_score_pairs.sort(key=lambda x: x[1], reverse=True)
            
            # 截取 Top-N 个结果（N 由配置中的 TOP_N_RERANK 决定，默认 3）
            top_n_pairs = doc_score_pairs[:settings.TOP_N_RERANK]
            
            # 构建返回结果
            results = []
            for doc, score in top_n_pairs:
                results.append({
                    "content": doc.page_content,
                    "score": float(score)
                })
            
            return results
            
        except Exception as e:
            raise Exception(f"检索失败: {str(e)}")


# 全局高级检索器实例
advanced_retriever = AdvancedRetriever()