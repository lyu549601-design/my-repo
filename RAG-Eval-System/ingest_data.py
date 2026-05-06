"""
数据入库脚本
调用 DocumentProcessor 将 PDF 文档切分并向量化存储到 Chroma 数据库
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.ingestion import DocumentProcessor


def main():
    """主函数：处理 PDF 文档并入库"""
    
    # PDF 文件路径
    pdf_path = "./data/心理咨询规章制度.pdf"
    
    # 检查文件是否存在
    if not os.path.exists(pdf_path):
        print(f"错误：PDF 文件不存在: {pdf_path}")
        print("请先运行 create_test_pdf.py 创建测试 PDF 文件")
        return
    
    try:
        print("=" * 50)
        print("开始处理 PDF 文档...")
        print(f"文件路径: {pdf_path}")
        print("=" * 50)
        
        # 创建文档处理器实例
        processor = DocumentProcessor()
        
        # 处理 PDF 文档并入库
        chunk_count = processor.process_and_store(pdf_path)
        
        print("=" * 50)
        print(f"文档处理完成！")
        print(f"成功入库的文本块数量: {chunk_count}")
        print(f"Chroma 数据库位置: ./data/chroma_db")
        print("=" * 50)
        
    except Exception as e:
        print(f"错误：文档处理失败: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()