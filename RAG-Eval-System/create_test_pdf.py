"""
创建测试 PDF 文件
生成心理咨询规章制度 PDF 文档
"""

from fpdf import FPDF
import os


def create_psychology_regulations_pdf():
    """创建心理咨询规章制度 PDF 文件"""
    
    # 确保 data 目录存在
    os.makedirs("./data", exist_ok=True)
    
    # PDF 文件路径
    pdf_path = "./data/心理咨询规章制度.pdf"
    
    # 创建 PDF 对象
    pdf = FPDF()
    pdf.add_page()
    
    # 使用内置字体
    pdf.set_font("Helvetica", size=12)
    
    # 标题
    pdf.set_font_size(24)
    pdf.cell(0, 20, text="Psychological Counseling Regulations", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    
    # 副标题
    pdf.set_font_size(16)
    pdf.cell(0, 10, text="Psychological Counseling Institution Regulations", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(20)
    
    # 章节内容
    chapters = [
        {
            "title": "Chapter 1: General Provisions",
            "content": [
                "Article 1: These regulations are formulated to standardize psychological counseling services and protect the legitimate rights and interests of clients.",
                "Article 2: These regulations apply to all psychological counseling activities conducted within the institution.",
                "Article 3: Psychological counseling shall adhere to the principles of professionalism, confidentiality, respect, and non-discrimination.",
                "Article 4: Counselors must possess relevant professional qualifications and engage in practice within their competence."
            ]
        },
        {
            "title": "Chapter 2: Scope of Counseling Services",
            "content": [
                "Article 5: Counseling services include but are not limited to: emotional management, interpersonal relationships, career planning, marriage and family issues, adolescent development, and stress coping.",
                "Article 6: Counseling does not include psychiatric diagnosis, medication prescription, or crisis intervention beyond professional competence.",
                "Article 7: For clients requiring medical intervention, counselors shall refer them to qualified psychiatric institutions."
            ]
        },
        {
            "title": "Chapter 3: Counselor Qualifications",
            "content": [
                "Article 8: Counselors must hold a national psychological counselor certificate or above, or a master's degree or above in psychology.",
                "Article 9: Counselors must receive no less than 100 hours of professional supervision annually.",
                "Article 10: Counselors must participate in continuing education and professional training to maintain professional competence.",
                "Article 11: Counselors must comply with professional ethics and shall not engage in dual relationships with clients."
            ]
        },
        {
            "title": "Chapter 4: Counseling Process",
            "content": [
                "Article 12: Initial consultation shall include: informed consent, goal setting, assessment of current situation, and development of counseling plan.",
                "Article 13: Each counseling session typically lasts 50 minutes, with frequency determined by client needs and counselor recommendations.",
                "Article 14: Counselors shall regularly evaluate counseling effectiveness and adjust plans as necessary.",
                "Article 15: Counseling termination shall be decided through mutual agreement between counselor and client, with appropriate referral arrangements."
            ]
        },
        {
            "title": "Chapter 5: Confidentiality Principles",
            "content": [
                "Article 16: Counselors must strictly maintain confidentiality of all client information, including counseling content, personal information, and assessment results.",
                "Article 17: Exceptions to confidentiality include: client poses danger to self or others, legal requirements, or client consent for specific disclosure.",
                "Article 18: Case records must be stored securely and accessed only by authorized personnel.",
                "Article 19: For teaching or research purposes, client information must be anonymized and consent obtained."
            ]
        },
        {
            "title": "Chapter 6: Disclaimers",
            "content": [
                "Article 20: Counseling outcomes depend on various factors; counselors cannot guarantee specific results.",
                "Article 21: Clients have the right to terminate counseling at any time, but should communicate with counselor regarding termination decisions.",
                "Article 22: Counselors are not liable for outcomes resulting from client's failure to follow professional recommendations.",
                "Article 23: In emergency situations, counselors may take necessary measures to protect client safety, with subsequent documentation and reporting."
            ]
        }
    ]
    
    # 写入章节内容
    for chapter in chapters:
        # 章节标题
        pdf.set_font_size(14)
        pdf.cell(0, 10, text=chapter["title"], new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)
        
        # 章节内容
        pdf.set_font_size(11)
        for article in chapter["content"]:
            pdf.multi_cell(0, 6, text=article)
            pdf.ln(3)
        
        pdf.ln(10)
    
    # 附则
    pdf.set_font_size(14)
    pdf.cell(0, 10, text="Supplementary Provisions", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font_size(11)
    supplementary = [
        "Article 24: These regulations shall come into effect on the date of promulgation.",
        "Article 25: The institution reserves the right to interpret and amend these regulations.",
        "Article 26: Any matters not covered by these regulations shall be handled in accordance with relevant national laws and regulations."
    ]
    
    for article in supplementary:
        pdf.multi_cell(0, 6, text=article)
        pdf.ln(3)
    
    # 保存 PDF
    pdf.output(pdf_path)
    print(f"PDF 文件已创建: {pdf_path}")
    
    return pdf_path


if __name__ == "__main__":
    create_psychology_regulations_pdf()