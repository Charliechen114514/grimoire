# 任务交接：把两本扫描版教材 PDF 转成「准确的 Markdown + 图」

> 这是一份自包含交接文档。前一个 AI 已完成全部可行性验证，以下均为**实测确认的事实**，可直接采信，不必重新推导。

## 1. 任务目标
把两个 PDF 教材转成交互式教程用的 Markdown（正文 + LaTeX 公式 + 表格 + 电路图嵌入）：
- `/home/charliechen/tutorial_summon/Electonic.pdf`（电子学第二版·霍罗威茨，928 页，68M）
- `/home/charliechen/tutorial_summon/Fundamentals_of_Power_Electronics.pdf`（Erickson，900 页，57M）
所属项目 `tutorial_summon`：PDF/网页→教程的 AI 生成管线（Python 3.12，`anthropic` SDK 调智谱，详见 `CLAUDE.md`）。

## 2. 已验证的核心事实（直接采信）
- **两本都是纯扫描书，PDF 无文字层**。每页就是一张扫描图。`get_text()` 对电子学只返回 5 字符（水印），对电力电子只返回 ebrary 水印引用。**项目现有 `pdf_parser.py`/`pdf_images.py` 无法处理**（它们假设生数字版有文字层；`pdf_images.py` 还会把 >80% 占比的全页图当扫描页跳过）。
- **电子学 PDF 有 xref 损坏**（`cannot find object in xref 769/1557/2629…`）。处理前用 `pymupdf.open().save(out, garbage=4, deflate=True)` 温和修复——**千万别用 `clean=True`，会崩**。残缺的是元数据/大纲对象，页面本身完好。
- **电子学 PDF 页面尺寸异常大（1490×2280pt ≈ 20.7"×31.7"）**，是正常书页 ~3 倍。任何按 DPI 渲染的工具（Marker）会生成 ~4000×6000 巨图，内存/显存爆。**必须先降采样到标准页（~1400px 宽 / 612pt）再处理。** 电力电子是标准 A4，无此问题。

## 3. 推荐方案：视觉 LLM 逐页（已逐字验证）⭐
**不要走 Marker（太慢）。走智谱视觉模型 glm-4.5v / glm-4v-plus。**

### ⚠️ 最关键的坑（前一个 AI 亲测踩中）
智谱有两条端点：
- **Anthropic 兼容端点 `/api/anthropic`（项目现在用的）→ 会静默丢弃图像！** 发 image+text，input 只有 ~200 token（图没传进去），glm-4.7 凭空幻觉出像模像样但完全错误的内容。**项目现有 `base_agent.py` 这条路绝对不能用来跑视觉。**
- **OpenAI 兼容端点 `/api/paas/v4/chat/completions` → 正确，图像真传进去了。** glm-4.5v 转写扫描页与前一个 AI 用 Marker 独立跑出的结果**一字不差**，页码、公式全对。

### 正确的视觉调用方式（已验证可用，直接复用）
```python
# .env: ANTHROPIC_API_KEY=<智谱key>, ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
import base64, httpx, os
from dotenv import load_dotenv
load_dotenv("/home/charliechen/tutorial_summon/.env", override=True)  # 脚本若在 /tmp 必须显式指定路径
API_KEY = os.getenv("ANTHROPIC_API_KEY")
b64 = base64.b64encode(open("page.png","rb").read()).decode()
r = httpx.post(
    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json={"model": "glm-4.5v",  # 或 glm-4v-plus（更快更便宜）
          "messages":[{"role":"user","content":[
              {"type":"image_url","image_url":{"url":f"data:image/png;base64,{b64}"}},
              {"type":"text","text":"把这页教材转成Markdown：正文照录，公式用LaTeX，表格保留，电路图位置标注[图]。只输出Markdown。"}]}]},
    timeout=120)
content = r.json()["choices"][0]["message"]["content"]
usage = r.json().get("usage")  # prompt_tokens / completion_tokens
```

### 成本/速度（实测）
| 模型 | 单页 token(入/出) | 全书1828页 | 速度 |
|---|---|---|---|
| glm-4v-plus | ~2400/~800 | **≈¥5-15** | ~5s/页 |
| glm-4.5v（旗舰质量） | ~3900/~1000 | **≈¥50-60**（Batch半价~¥28） | ~27s/页 |
- 🎁 智谱新用户送 2000 万 token，按 ~5000/页算够 ~4000 页，**可能直接免费**。
- 全程走**用户自己的智谱账户**，**不走 MCP**，跟现有 text agent 同一本账。

## 4. 备选方案：Marker（仅离线/无额度兜底）
- 已装：`marker-pdf 1.10.2`，torch 2.12+cu130，**RTX 3060 6GB（CUDA 可用）**。
- 质量 ~90%：中文 OCR 准、公式→LaTeX、电路图自动裁切嵌入（裁切评分 8/10）。
- **致命短板：慢**。~6 分钟/页，且文字识别每块耗时从 5s 涨到 123s（笔记本 GPU 热降频）。全书不可行。**且必须先降采样页面**（否则内存 8.7G/11G 爆）。
- CLI：`.venv/bin/marker_single input.pdf --output_dir OUT --force_ocr --highres_image_dpi 150 --lowres_image_dpi 72`

## 5. 项目架构要点（接哪里）
- **强制用 `.venv`**：`source .venv/bin/activate`（见 `CLAUDE.md`）。
- API 配置：`src/config.py`（`ANTHROPIC_API_KEY`/`ANTHROPIC_BASE_URL`/`MODEL_ALIASES`：haiku/sonnet/opus）+ `.env`。`GRIMOIRE_MODEL=sonnet` → 发 `claude-sonnet-4-6-20250514` → 智谱映射成 `glm-4.7`。
- `src/agents/base_agent.py`：`anthropic` SDK，**纯文本**（`messages=[{role,content:str}]`）。视觉需新增 OpenAI 兼容调用路径。
- `src/parsers/pdf_parser.py`（文字层）、`pdf_images.py`（图块提取，跳过 >80% 全页图）、`base.py`（BaseParser）、`__init__.py`（工厂）。
- `src/schema.py`：`ChaptersRaw`/`SourceMeta`/`TocEntry`。`config.py`：`book_data_dir()`/`book_output_dir()`/路径常量。
- `cli.py`：parse/batch/review/package/all 子命令。`src/batch.py`（并行）、`progress.py`（断点续跑）、`review.py`（质量审查+autofix）。

## 6. 现成实验产物（在 /tmp，可直接复用/查看）
- `/tmp/vision_verify.py` —— **最有价值**：已验证 glm-4.5v/glm-4v-plus 真看图、逐字正确的脚本。视觉调用照抄它。
- `/tmp/marker_pilot/`：`Elec_ch02_transistors.pdf`（43页干净切片）、`PE_ch06_converter_circuits.pdf`（54页）、`elec_3page.pdf`（降采样3页）、`out_elec3/elec_3page.md`（Marker 产出 + 7 张电路图）。
- `/tmp/vtest/`：5 张已渲染测试页 PNG（elec_p5/12/20、pe_p5/15）。
- `/tmp/slice_pdfs.py`（切章+温和修复）、`/tmp/make_3page.py`（页面降采样）、`/tmp/probe_pdf.py`（PDF 性质探针）。
- 项目记忆已写入 `~/.claude/projects/-home-charliechen-tutorial-summon/memory/`（`target-pdfs-are-pure-scans`、`scanned-pdf-conversion-strategy`、`zhipu-vision-endpoint-gotcha`）——若下一个 AI 是同项目的 Claude Code 会自动加载。

## 7. 下一步建议（待用户确认的具体动作）
搭一个**最小视觉转换器**：渲染每页→PNG（电子学页降采样到 ~1400px）→glm-4.5v 转写→拼 Markdown。**先在电力电子 Ch6 前 10 页端到端跑通**（成本 ~¥1），让用户看完整成品质量，再决定全书铺开 + 工程化（分章、并发、断点续跑复用 `progress.py`、质量校验）。
图的处理策略：电路图走"裁切原图嵌入"（Marker 那套），文字/公式/表格走视觉转写。

## 8. 务必遵守
- 任何 Python 命令走 `.venv`。
- 视觉调用**只用 OpenAI 兼容端点**，别碰 Anthropic 兼容端点（丢图）。
- 处理电子学前先温和修复 + 降采样页面。
- Marker 若用，小批量 + 留散热间隔。
- 视觉输出要做**忠实性校验**（glm-4.7 经错误端点曾整页幻觉，别轻信未校验的"成功"）。
