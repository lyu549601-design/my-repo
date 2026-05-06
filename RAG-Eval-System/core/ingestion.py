"""
文档处理模块
负责文档的读取、切分和向量化存储
"""

import os
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document

from core.config import settings


class DocumentProcessor:
    """
    文档处理器
    负责将 PDF 文档切分并向量化存储到 Chroma 数据库
    """
    
    def __init__(self):
        """
        初始化文档处理器
        创建必要的目录和 Embedding 模型实例
        """
        # 确保 Chroma 数据库目录存在
        self.chroma_dir = "./data/chroma_db"
        os.makedirs(self.chroma_dir, exist_ok=True)
        
        # 初始化 BGE Embedding 模型
        # 使用中文优化的 BGE 模型进行文本向量化
        self.embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-small-zh-v1.5",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        
        # 初始化文本分割器
        # 使用递归字符分割器，根据配置的 chunk_size 和 chunk_overlap 进行切分
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
        )
    
    def process_and_store(self, file_path: str) -> int:
        """
        处理 PDF 文档并存储到向量数据库
        
        Args:
            file_path: PDF 文件路径
            
        Returns:
            int: 成功存入的 Chunk 数量
            
        Raises:
            FileNotFoundError: 文件不存在
            Exception: 文档处理或存储失败
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 检查文件是否为 PDF
            if not file_path.lower().endswith('.pdf'):
                raise ValueError(f"不支持的文件格式，仅支持 PDF 文件: {file_path}")
            
            # 加载 PDF 文档
            loader = PyPDFLoader(file_path)
            documents = loader.load()
            
            if not documents:
                raise ValueError(f"PDF 文件为空或无法读取: {file_path}")
            
            # 切分文档
            chunks = self.text_splitter.split_documents(documents)
            
            if not chunks:
                raise ValueError(f"文档切分后无有效内容: {file_path}")
            
            # 存储到 Chroma 数据库
            # 使用持久化存储，数据将保存在 ./data/chroma_db 目录
            vectorstore = Chroma.from_documents(
                documents=chunks,
                embedding=self.embeddings,
                persist_directory=self.chroma_dir,
                collection_name="rag_documents"
            )
            
            # 持久化数据库
            vectorstore.persist()
            
            # 返回成功存入的 Chunk 数量
            return len(chunks)
            
        except FileNotFoundError as e:
            # 文件不存在异常
            raise e
        except ValueError as e:
            # 值错误异常
            raise e
        except Exception as e:
            # 其他异常
            raise Exception(f"文档处理失败: {str(e)}")
    
    def get_retriever(self):
        """
        获取向量检索器
        
        Returns:
            VectorStoreRetriever: 向量检索器实例
        """
        try:
            # 连接到已存在的 Chroma 数据库
            vectorstore = Chroma(
                persist_directory=self.chroma_dir,
                embedding_function=self.embeddings,
                collection_name="rag_documents"
            )
            
            # 返回检索器
            return vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={"k": settings.TOP_K_RETRIEVAL}
            )
            
        except Exception as e:
            raise Exception(f"获取检索器失败: {str(e)}")


# 全局文档处理器实例
document_processor = DocumentProcessor()