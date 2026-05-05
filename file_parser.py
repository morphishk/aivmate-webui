"""文件解析模块：支持 PDF、DOCX、TXT、MD 文本提取"""

import os


class FileParserError(Exception):
    """文件解析异常基类"""
    pass


def parse_pdf(file_path: str) -> tuple[str, bool]:
    """解析 PDF，返回 (文本内容, 是否被截断)"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if not text.strip():
            # 可能是扫描件（无文本层）
            return "", False
        truncated = len(text) > 100000
        return text[:100000], truncated
    except ImportError:
        raise FileParserError("请安装 pdfplumber: pip install pdfplumber")
    except Exception as e:
        raise FileParserError(f"PDF 解析失败: {e}")


def parse_docx(file_path: str) -> tuple[str, bool]:
    """解析 DOCX，返回 (文本内容, 是否被截断)"""
    try:
        import docx
        document = docx.Document(file_path)
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        truncated = len(text) > 100000
        return text[:100000], truncated
    except ImportError:
        raise FileParserError("请安装 python-docx: pip install python-docx")
    except Exception as e:
        raise FileParserError(f"DOCX 解析失败: {e}")


def parse_txt(file_path: str) -> tuple[str, bool]:
    """解析 TXT/MD"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        truncated = len(text) > 100000
        return text[:100000], truncated
    except Exception as e:
        raise FileParserError(f"文本读取失败: {e}")


def parse_file(file_path: str) -> tuple[str, bool]:
    """根据扩展名分发解析"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return parse_pdf(file_path)
    elif ext == ".docx":
        return parse_docx(file_path)
    elif ext in (".txt", ".md"):
        return parse_txt(file_path)
    else:
        raise FileParserError(f"不支持的文件格式: {ext}")


def check_dependencies() -> dict[str, bool]:
    """检查解析依赖是否已安装"""
    deps = {}
    try:
        import pdfplumber
        deps["pdfplumber"] = True
    except ImportError:
        deps["pdfplumber"] = False
    try:
        import docx
        deps["python-docx"] = True
    except ImportError:
        deps["python-docx"] = False
    return deps
