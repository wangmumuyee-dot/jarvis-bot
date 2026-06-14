import fs from "node:fs";
import path from "node:path";

const root = "/Users/xuwangmumu/Documents/obsidian/王木木学习资料";
const today = "2026-06-12";

function full(rel) {
  return path.join(root, rel);
}

function ensureDir(rel) {
  fs.mkdirSync(full(rel), { recursive: true });
}

function yamlValue(value) {
  if (Array.isArray(value)) {
    if (value.length === 0) return "";
    return "\n" + value.map((item) => `  - ${item}`).join("\n");
  }
  return value ?? "";
}

function frontmatter(meta) {
  const fields = {
    type: meta.type,
    status: meta.status,
    owner: meta.owner ?? "mixed",
    summary: meta.summary,
    source: meta.source ?? "",
    tags: meta.tags ?? [],
  };
  const lines = ["---"];
  for (const [key, value] of Object.entries(fields)) {
    const rendered = yamlValue(value);
    if (typeof rendered === "string" && rendered.startsWith("\n")) {
      lines.push(`${key}:${rendered}`);
    } else {
      lines.push(`${key}: ${rendered}`);
    }
  }
  lines.push("---", "");
  return lines.join("\n");
}

function writeNote(rel, meta, body) {
  ensureDir(path.dirname(rel));
  fs.writeFileSync(full(rel), frontmatter(meta) + body.trimStart() + "\n", "utf8");
}

function writeIfMissing(rel, meta, body) {
  if (!fs.existsSync(full(rel))) writeNote(rel, meta, body);
}

function read(rel) {
  return fs.readFileSync(full(rel), "utf8");
}

function write(rel, content) {
  ensureDir(path.dirname(rel));
  fs.writeFileSync(full(rel), content, "utf8");
}

function appendSection(rel, heading, body) {
  let content = read(rel);
  if (content.includes(`## ${heading}`)) return;
  content = content.trimEnd() + `\n\n## ${heading}\n${body.trim()}\n`;
  write(rel, content);
}

function replaceBodyAfterFrontmatter(rel, body) {
  const content = read(rel);
  const match = content.match(/^---\n[\s\S]*?\n---\n/);
  if (!match) throw new Error(`Missing frontmatter: ${rel}`);
  write(rel, match[0] + body.trimStart() + "\n");
}

function appendLog(entry) {
  const rel = "00_System/log.md";
  const content = read(rel);
  if (content.includes(entry.trim())) return;
  write(rel, content.trimEnd() + "\n\n" + entry.trim() + "\n");
}

function updateAreaIndex(rel, body) {
  appendSection(rel, "现有核心笔记", body);
}

const notes = {
  gradient: "30_Areas/AI与工具/概念/梯度消失与梯度爆炸.md",
  gstack: "30_Areas/AI与工具/工具/gstack.md",
  growth: "30_Areas/个人成长/方法/用6个月超过99%的人.md",
  growthSource: "30_Areas/个人成长/资料/收藏整理.md",
  eye: "30_Areas/健康与身体/方法/眼球训练.md",
  shoulder: "30_Areas/健康与身体/方法/翼状肩胛.md",
  head: "30_Areas/健康与身体/经验/头顶上颚.md",
  media: "30_Areas/输入与审美/书影音/书影音清单.md",
};

appendSection(
  notes.gradient,
  "相关笔记",
  `- [[gstack]]：AI 工具工作流层面的实践笔记。
- [[学习 AI 与 LLM 基础]]：把深度学习基础概念系统化的项目。`,
);
appendSection(
  notes.gradient,
  "可复用价值",
  `- 可输出：用生活化比喻解释梯度消失、梯度爆炸和残差连接。
- 可行动：补充反向传播、激活函数、归一化、Transformer 残差等相关概念。
- 可连接：连接到 AI 基础学习路线、模型训练稳定性、深度学习入门内容。`,
);

appendSection(
  notes.gstack,
  "相关笔记",
  `- [[梯度消失与梯度爆炸]]：AI 基础概念线。
- [[建立 AI 辅助工作流]]：把 AI 工具方法转成个人工作流的项目。
- [[是否用 Skill 化工作流管理 AI 协作]]：关于 AI 协作方式的工具选型决策。`,
);
appendSection(
  notes.gstack,
  "可复用价值",
  `- 可输出：拆解“AI 工具不是插件，而是工作流治理层”的观点。
- 可行动：为自己的 Codex / Claude / Obsidian 协作设计角色分工。
- 可连接：连接到软件开发流程、个人自动化、AI 代理协作。`,
);

appendSection(
  notes.growthSource,
  "相关笔记",
  `- [[用6个月超过99%的人]]：这条资料已整理成个人成长方法笔记。
- [[6个月个人成长实验]]：把方法转成可执行项目。`,
);
appendSection(
  notes.growthSource,
  "可复用价值",
  `- 可输出：从一个短视频链接拆出一篇个人成长方法论内容。
- 可行动：继续追踪原始来源，补齐作者观点和自己的验证记录。
- 可连接：连接到反愿景、长期主义、个人系统建设。`,
);

appendSection(
  notes.growth,
  "相关笔记",
  `- [[收藏整理]]：原始来源记录。
- [[6个月个人成长实验]]：把这套方法落成行动项目。
- [[是否启动6个月个人成长实验]]：记录是否采用这套方法的判断。`,
);
appendSection(
  notes.growth,
  "可复用价值",
  `- 可输出：小红书选题“先写反愿景，再谈自律”。
- 可行动：把愿景拆成月/周/日目标，并建立 2-3 天一次的复盘节奏。
- 可连接：连接到人生实验、抗熵增、内容定位、项目管理。`,
);

appendSection(
  notes.eye,
  "相关笔记",
  `- [[头顶上颚]]：头颈中线与眼动训练相关。
- [[翼状肩胛]]：身体训练和体态改善相关。
- [[身体训练与体态改善]]：健康与身体领域的行动项目。`,
);
appendSection(
  notes.eye,
  "可复用价值",
  `- 可输出：整理成“每天 5 分钟改善视觉稳定”的健康内容。
- 可行动：记录训练频率、眩晕/疲劳反应和 1-2 周效果。
- 可连接：连接到前庭眼反射、用眼疲劳、屏幕工作者身体维护。`,
);

appendSection(
  notes.shoulder,
  "相关笔记",
  `- [[头顶上颚]]：头颈位置与体态链条相关。
- [[眼球训练]]：身体稳定性和视觉稳定相关。
- [[身体训练与体态改善]]：健康与身体领域的行动项目。`,
);
appendSection(
  notes.shoulder,
  "可复用价值",
  `- 可输出：整理成“翼状肩胛可能和呼吸模式有关”的健康科普内容。
- 可行动：建立每天三组训练记录，观察肩颈酸胀和体态变化。
- 可连接：连接到呼吸模式、前锯肌、肩颈问题、久坐改善。`,
);

appendSection(
  notes.head,
  "相关笔记",
  `- [[眼球训练]]：眼动训练与头颈中线控制相关。
- [[翼状肩胛]]：体态、呼吸和头颈位置相关。
- [[身体训练与体态改善]]：健康与身体领域的行动项目。`,
);
appendSection(
  notes.head,
  "可复用价值",
  `- 可输出：整理成“舌抵上腭如何帮助找回头颈中线感”的健康内容。
- 可行动：记录靠墙练习、退阶调整和眼动训练后的身体反馈。
- 可连接：连接到头前伸、颈椎压力、眼压、体态改善。`,
);

appendSection(
  notes.media,
  "相关笔记",
  `- [[输入与审美]]：领域首页。
- [[建立输入与审美清单]]：把书影音输入转成长期审美资产的项目。`,
);
appendSection(
  notes.media,
  "可复用价值",
  `- 可输出：定期整理观看/阅读清单和审美偏好变化。
- 可行动：给每条输入补充“为什么想看/看完得到什么”。
- 可连接：连接到写作素材、内容表达、审美训练。`,
);

updateAreaIndex(
  "30_Areas/AI与工具/_index.md",
  `- [[梯度消失与梯度爆炸]]：深度学习训练稳定性的基础概念。
- [[gstack]]：AI 协作工作流与技能化 agent 的案例。
- [[学习 AI 与 LLM 基础]]：把 AI 基础概念持续系统化。
- [[建立 AI 辅助工作流]]：把 AI 工具转化成个人生产系统。`,
);

updateAreaIndex(
  "30_Areas/个人成长/_index.md",
  `- [[用6个月超过99%的人]]：反愿景、抗熵增系统、长期主义。
- [[收藏整理]]：Dan Koe 视频来源记录。
- [[6个月个人成长实验]]：将个人成长方法转为行动项目。
- [[是否启动6个月个人成长实验]]：记录是否采用该实验的决策过程。`,
);

updateAreaIndex(
  "30_Areas/健康与身体/_index.md",
  `- [[眼球训练]]：前庭与眼球协同训练。
- [[翼状肩胛]]：呼吸模式与肩胛稳定。
- [[头顶上颚]]：头颈中线与舌抵上腭练习。
- [[身体训练与体态改善]]：将训练笔记转成持续行动项目。`,
);

updateAreaIndex(
  "30_Areas/输入与审美/_index.md",
  `- [[书影音清单]]：长期输入列表。
- [[建立输入与审美清单]]：把输入记录升级为审美资产。`,
);

updateAreaIndex(
  "30_Areas/自媒体与变现/_index.md",
  `- [[小红书/选题池]]：轻量图文选题。
- [[公众号/选题池]]：长文选题。
- [[抖音/选题池]]：视频脚本选题。
- [[是否把 Life Wiki 作为内容生产系统]]：内容系统化方向决策。`,
);

writeIfMissing(
  "40_Projects/Active/学习 AI 与 LLM 基础.md",
  {
    type: "project",
    status: "growing",
    owner: "mixed",
    summary: "系统学习 AI 与 LLM 基础概念，并把每个概念沉淀为可复用笔记和内容素材。",
    tags: ["AI", "学习项目"],
  },
  `# 学习 AI 与 LLM 基础

## 目标
把 AI 与 LLM 的基础概念整理成一套能复习、能输出、能指导实践的个人知识地图。

## 为什么重要
AI 是当前知识库的核心长期领域之一。概念理解越清楚，后续使用工具、做内容、做自动化都会更稳。

## 当前状态
- 已有 [[梯度消失与梯度爆炸]]
- 已有 [[gstack]]

## 下一步
- 补充反向传播、激活函数、残差连接、注意力机制、Transformer 等概念。
- 每个概念页都补“可输出 / 可行动 / 可连接”。

## 相关笔记
- [[梯度消失与梯度爆炸]]
- [[gstack]]
- [[AI与工具]]

## 复盘
- 每 2-3 天维护时检查新增概念是否进入领域首页。
`,
);

writeIfMissing(
  "40_Projects/Active/建立 AI 辅助工作流.md",
  {
    type: "project",
    status: "growing",
    owner: "mixed",
    summary: "把 Codex、Obsidian、Skill 化工作流整合成稳定的个人知识与创作系统。",
    tags: ["AI工具", "工作流"],
  },
  `# 建立 AI 辅助工作流

## 目标
让 AI 不只是回答问题，而是参与知识库维护、内容转化、项目推进和决策复盘。

## 为什么重要
这能把输入、思考、行动和输出连起来，让知识库变成持续运转的 Life Wiki。

## 当前状态
- 已建立 [[AGENTS]]
- 已建立 [[maintenance-protocol]]
- 已整理 [[gstack]]

## 下一步
- 固定每 2-3 天维护一次。
- 观察哪些任务适合交给 LLM，哪些必须保留用户原声。
- 设计常用命令：整理 Inbox、生成选题、复盘项目、更新决策。

## 相关笔记
- [[gstack]]
- [[AGENTS]]
- [[maintenance-protocol]]

## 复盘
- 记录每次维护节省了什么时间、产生了什么输出、哪里需要人工判断。
`,
);

writeIfMissing(
  "40_Projects/Active/6个月个人成长实验.md",
  {
    type: "project",
    status: "growing",
    owner: "mixed",
    summary: "把反愿景、抗熵增系统和长期主义转成一个可执行的 6 个月成长实验。",
    tags: ["个人成长", "人生实验"],
  },
  `# 6个月个人成长实验

## 目标
用 6 个月验证一套个人成长系统：反愿景、目标拆解、切割阻碍、周期复盘。

## 为什么重要
这能把“想变好”变成具体实验，而不是停留在收藏和鸡血。

## 当前状态
- 已有 [[用6个月超过99%的人]]
- 已有 [[收藏整理]]

## 下一步
- 写一页反愿景：明确不想过的生活。
- 设定本月、本周、今天的可执行目标。
- 每 2-3 天复盘一次。

## 相关笔记
- [[用6个月超过99%的人]]
- [[是否启动6个月个人成长实验]]

## 复盘
- 复盘关注：是否行动、是否调整环境、是否产生真实输出。
`,
);

writeIfMissing(
  "40_Projects/Active/身体训练与体态改善.md",
  {
    type: "project",
    status: "growing",
    owner: "mixed",
    summary: "把眼球训练、头颈中线和肩胛改善笔记转成可持续记录的身体训练项目。",
    tags: ["健康", "训练"],
  },
  `# 身体训练与体态改善

## 目标
用低成本、可记录的训练改善视觉稳定、头颈位置、肩颈状态和体态控制。

## 为什么重要
身体状态会直接影响学习、工作、内容创作和长期行动力。

## 当前状态
- 已有 [[眼球训练]]
- 已有 [[头顶上颚]]
- 已有 [[翼状肩胛]]

## 下一步
- 选择一套每天 5-10 分钟的基础训练。
- 记录训练前后的疲劳、眩晕、肩颈感受。
- 两周后复盘是否继续、调整或停止。

## 相关笔记
- [[眼球训练]]
- [[头顶上颚]]
- [[翼状肩胛]]

## 复盘
- 复盘关注：症状变化、动作安全性、是否需要专业建议。
`,
);

writeIfMissing(
  "40_Projects/Active/建立输入与审美清单.md",
  {
    type: "project",
    status: "seed",
    owner: "mixed",
    summary: "把书影音清单从待看列表升级为可积累审美、写作素材和内容灵感的输入系统。",
    tags: ["输入", "审美"],
  },
  `# 建立输入与审美清单

## 目标
持续记录书影音输入，并沉淀自己的审美偏好、观点和表达素材。

## 为什么重要
输入质量会影响写作、表达和内容创作的厚度。

## 当前状态
- 已有 [[书影音清单]]

## 下一步
- 每条清单补“为什么想看/想读”。
- 看完后补一句“我获得了什么”。
- 从输入中抽取可用于小红书、公众号、抖音的内容素材。

## 相关笔记
- [[书影音清单]]
- [[输入与审美]]

## 复盘
- 每月检查输入是否真的转化为观点、素材或作品。
`,
);

writeIfMissing(
  "70_Decisions/工具选型/是否用 Skill 化工作流管理 AI 协作.md",
  {
    type: "decision",
    status: "growing",
    owner: "mixed",
    summary: "记录是否借鉴 gstack 思路，用 Skill 化角色和流程管理 AI 协作。",
    tags: ["AI工具", "决策"],
  },
  `# 是否用 Skill 化工作流管理 AI 协作

## 背景
[[gstack]] 展示了一种把 AI 变成多角色协作流程的方式，而不是只把 AI 当成聊天工具。

## 选项
- 继续临时提问式使用 AI。
- 建立固定技能和流程，让 AI 承担规划、整理、评审、输出、复盘等不同角色。

## 判断标准
- 是否降低维护知识库的阻力。
- 是否提升内容产出质量。
- 是否保护用户原始表达和判断。

## 当前决定
倾向采用，但先从 Obsidian Life Wiki 的维护流程开始验证。

## 预期结果
每 2-3 天维护一次，能稳定完成 Inbox 清理、双链补全、选题生成和项目复盘。

## 复盘日期
待定。

## 复盘结果
待补充。
`,
);

writeIfMissing(
  "70_Decisions/副业/是否把 Life Wiki 作为内容生产系统.md",
  {
    type: "decision",
    status: "growing",
    owner: "mixed",
    summary: "记录是否把 Obsidian Life Wiki 作为小红书、公众号和抖音内容生产的底层系统。",
    tags: ["自媒体", "决策"],
  },
  `# 是否把 Life Wiki 作为内容生产系统

## 背景
知识库已经同时覆盖 AI、职场、个人成长、健康、输入审美等领域，并建立了 [[60_Outputs]]。

## 选项
- 知识库只做个人学习整理。
- 知识库同时承担内容生产系统，持续生成选题、草稿和复盘。

## 判断标准
- 是否能减少从输入到输出的摩擦。
- 是否能帮助形成稳定内容定位。
- 是否能避免只收藏不产出。

## 当前决定
倾向采用，并先支持小红书、公众号和抖音三个平台。

## 预期结果
每次维护都至少产生若干个可验证选题，并逐步形成可发布草稿。

## 复盘日期
待定。

## 复盘结果
待补充。
`,
);

writeIfMissing(
  "70_Decisions/副业/是否启动6个月个人成长实验.md",
  {
    type: "decision",
    status: "seed",
    owner: "user",
    summary: "记录是否把 6 个月个人成长方法论变成实际行动实验。",
    tags: ["个人成长", "决策"],
  },
  `# 是否启动6个月个人成长实验

## 背景
[[用6个月超过99%的人]] 提到反愿景、抗熵增系统和长期主义，适合转成一个个人实验。

## 选项
- 只作为方法论收藏。
- 启动 6 个月实验，建立目标、行动和复盘节奏。

## 判断标准
- 是否有明确反愿景。
- 是否能拆成周行动。
- 是否愿意每 2-3 天复盘一次。

## 当前决定
待用户确认。

## 预期结果
如果启动，应形成持续行动记录和阶段复盘。

## 复盘日期
待定。

## 复盘结果
待补充。
`,
);

writeIfMissing(
  "70_Decisions/健康生活/是否建立身体训练复盘机制.md",
  {
    type: "decision",
    status: "seed",
    owner: "user",
    summary: "记录是否把零散身体训练笔记转成可复盘、可调整的健康训练机制。",
    tags: ["健康", "决策"],
  },
  `# 是否建立身体训练复盘机制

## 背景
目前已有 [[眼球训练]]、[[头顶上颚]]、[[翼状肩胛]] 等健康与身体笔记。

## 选项
- 需要时临时练习。
- 建立固定训练和两周复盘机制。

## 判断标准
- 动作是否安全。
- 是否能稳定执行。
- 是否能记录身体反馈并及时调整。

## 当前决定
待用户确认。

## 预期结果
训练不再停留在收藏，而是形成可观察的改善记录。

## 复盘日期
待定。

## 复盘结果
待补充。
`,
);

replaceBodyAfterFrontmatter(
  "60_Outputs/小红书/选题池.md",
  `# 小红书选题池

## 待选题
- [ ] 我把 Obsidian 改造成 Life Wiki：一个适合普通人的 AI 人生知识库结构
  - 来源：[[AGENTS]]、[[maintenance-protocol]]
  - 角度：知识库不是收藏夹，而是输入、行动、输出系统。
- [ ] 先写反愿景，再谈自律：我从“6个月超过99%的人”里提炼出的行动框架
  - 来源：[[用6个月超过99%的人]]
  - 角度：迷茫期先明确不想要的生活。
- [ ] AI 工具不是插件，是工作流：gstack 给我的启发
  - 来源：[[gstack]]
  - 角度：把 AI 当成虚拟团队，而不是万能聊天框。
- [ ] 每天 5 分钟眼球训练：屏幕党如何练视觉稳定
  - 来源：[[眼球训练]]
  - 角度：头动时眼睛还能稳住目标。
- [ ] 翼状肩胛可能不只是肩的问题，也可能和呼吸模式有关
  - 来源：[[翼状肩胛]]
  - 角度：从呼吸、肩胛稳定和久坐讲体态改善。
- [ ] 舌抵上腭如何帮我找到头颈中线感
  - 来源：[[头顶上颚]]
  - 角度：把身体感受写成可验证练习。

## 已进入草稿

## 已发布复盘
`,
);

replaceBodyAfterFrontmatter(
  "60_Outputs/公众号/选题池.md",
  `# 公众号选题池

## 待选题
- [ ] 从收藏夹到人生知识库：我的 Obsidian Life Wiki 搭建框架
  - 来源：[[AGENTS]]、[[maintenance-protocol]]、[[index]]
  - 结构：为什么做、目录设计、权限模型、维护流程、输出转化。
- [ ] gstack 与 AI 协作工作流：从工具使用到流程治理
  - 来源：[[gstack]]、[[建立 AI 辅助工作流]]
  - 结构：角色分工、生命周期、个人知识库中的应用。
- [ ] 用反愿景启动人生实验：6个月个人成长系统的第一版设计
  - 来源：[[用6个月超过99%的人]]、[[6个月个人成长实验]]
  - 结构：反愿景、实验期、目标拆解、复盘。
- [ ] 身体训练笔记：从眼球、肩胛到头颈中线
  - 来源：[[眼球训练]]、[[翼状肩胛]]、[[头顶上颚]]
  - 结构：三个训练主题、记录方式、安全边界、两周复盘。

## 已进入草稿

## 已发布复盘
`,
);

replaceBodyAfterFrontmatter(
  "60_Outputs/抖音/选题池.md",
  `# 抖音选题池

## 待选题
- [ ] 30 秒讲清楚：什么是 Obsidian Life Wiki
  - 来源：[[index]]、[[AGENTS]]
  - 开头：不要再把知识库当收藏夹了。
- [ ] 30 秒讲清楚：反愿景为什么比愿景更适合迷茫期
  - 来源：[[用6个月超过99%的人]]
  - 开头：迷茫的时候，先别问想要什么，先问不想要什么。
- [ ] 60 秒讲清楚：AI 工具为什么要流程化
  - 来源：[[gstack]]
  - 开头：AI 不是插件，AI 更像一个需要分工的团队。
- [ ] 30 秒演示：头动眼稳的眼球训练
  - 来源：[[眼球训练]]
  - 开头：如果你看屏幕容易累，可以先练这个基础动作。
- [ ] 60 秒讲清楚：翼状肩胛和呼吸模式的关系
  - 来源：[[翼状肩胛]]
  - 开头：有些体态问题，不一定只从肩膀开始改。

## 已进入脚本

## 已发布复盘
`,
);

appendSection(
  "40_Projects/_index.md",
  "Active 项目",
  `- [[学习 AI 与 LLM 基础]]
- [[建立 AI 辅助工作流]]
- [[6个月个人成长实验]]
- [[身体训练与体态改善]]
- [[建立输入与审美清单]]`,
);

appendSection(
  "70_Decisions/_index.md",
  "第一批决策",
  `- [[是否用 Skill 化工作流管理 AI 协作]]
- [[是否把 Life Wiki 作为内容生产系统]]
- [[是否启动6个月个人成长实验]]
- [[是否建立身体训练复盘机制]]`,
);

appendSection(
  "60_Outputs/_index.md",
  "第一批选题方向",
  `- Life Wiki / Obsidian / AI 知识库搭建
- AI 工具工作流与 gstack
- 6 个月个人成长实验
- 屏幕工作者健康训练
- 输入与审美清单`,
);

appendLog(`## ${today} 第二阶段
- 为现有核心笔记补充“相关笔记”和“可复用价值”。
- 更新 AI与工具、个人成长、健康与身体、输入与审美、自媒体与变现领域首页。
- 从现有内容提取小红书、公众号、抖音第一批选题。
- 创建第一批 Active 项目和决策页。`);

console.log("Life Wiki stage 2 enrichment complete.");
