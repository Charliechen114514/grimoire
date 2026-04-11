"""M3 质量门验证脚本 — 单 Agent 原型，验证写作风格是否达标。

用法：
    .venv/bin/python scripts/m3_prototype.py

输出：
    output/CSAPP/tutorials/ch01_prototype.md

人工验收后决定是否进入 M4。
"""
import json
import logging
import sys
from pathlib import Path

# 确保 project root 在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.base_agent import BaseAgent
from src.config import BOOKS_DIR, DATA_DIR, MAX_TOKENS, WRITING_STYLE_PATH

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


class PrototypeAgent(BaseAgent):
    """M3 原型 Agent — 直接用 writing_style.md 作为 system prompt 核心。"""

    def __init__(self) -> None:
        super().__init__("prototype")

    def run(self, chapter_text: str, chapter_idx: int) -> str:
        """生成单章教程原型。"""
        # system prompt = writing_style.md + 输出格式指令
        writing_style = WRITING_STYLE_PATH.read_text(encoding="utf-8")

        system_prompt = (
            writing_style
            + "\n\n---\n\n"
            "# 输出格式要求\n\n"
            "请基于下面的章节原文，生成一篇完整的中文教程文章。文章必须包含以下部分：\n\n"
            "1. **前言/动机段**：为什么这个章节的内容重要、学完能做什么\n"
            "2. **知识点讲解正文**：按章节内容分阶段推进，每个知识点都要有"
            "「为什么」的解释、类比说明、可能的踩坑点\n"
            "3. **练习题**：3-5 道练习题，难度从理解到应用到思考递进，每题附答案和解析\n"
            "4. **要点提炼**：不超过 5 条核心要点，用自然段落形式呈现\n\n"
            "输出为 Markdown 格式。严格遵循上面的写作风格指南。"
        )

        # 截取章节原文（避免超出 context window）
        max_chars = 60000
        text = chapter_text[:max_chars]
        if len(chapter_text) > max_chars:
            text += f"\n\n[... 原文已截断，完整长度 {len(chapter_text)} 字符 ...]"

        user_prompt = (
            f"# 第 {chapter_idx} 章原文\n\n"
            f"请将以下章节原文转化为符合上述写作风格的教程文章：\n\n"
            f"{text}"
        )

        logger.info("Calling API for chapter %d prototype...", chapter_idx)
        result = self.call_api(system=system_prompt, user=user_prompt, max_tokens=MAX_TOKENS)
        logger.info("API returned %d chars", len(result))
        return result


def main() -> None:
    # 加载 Ch1 原文
    chapters_path = DATA_DIR / "CSAPP" / "chapters_raw.json"
    chapters = json.loads(chapters_path.read_text(encoding="utf-8"))
    ch1_text = chapters["1"]
    logger.info("Loaded Ch1: %d chars", len(ch1_text))

    # 生成教程
    agent = PrototypeAgent()
    output = agent.run(chapter_text=ch1_text, chapter_idx=1)

    # 保存结果
    output_dir = Path(__file__).resolve().parent.parent / "output" / "CSAPP" / "tutorials"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "ch01_prototype.md"
    output_path.write_text(output, encoding="utf-8")

    logger.info("Prototype saved to: %s (%d chars)", output_path, len(output))
    print(f"\nOutput: {output_path}")
    print(f"Length: {len(output)} chars")
    print(f"\n--- Preview (first 500 chars) ---\n{output[:500]}")


if __name__ == "__main__":
    main()
