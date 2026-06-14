import fs from "node:fs";
import path from "node:path";

const root = "/Users/xuwangmumu/Documents/obsidian/王木木学习资料";
const today = "2026-06-12";

const areas = {
  "AI与工具": ["概念", "工具", "方法", "资料", "问题"],
  "职场与工作": ["经验", "方法", "案例", "资料", "问题"],
  "个人成长": ["经验", "方法", "资料", "问题"],
  "自媒体与变现": ["选题", "方法", "案例", "资料", "问题"],
  "写作与表达": ["经验", "方法", "素材", "资料", "问题"],
  "财务与商业": ["经验", "方法", "资料", "问题"],
  "健康与身体": ["经验", "方法", "资料", "问题"],
  "生活与关系": ["经验", "方法", "资料", "问题"],
  "输入与审美": ["书影音", "资料", "灵感", "问题"],
};

const migrations = [
  {
    from: "AI学习/基础知识/梯度.md",
    to: "30_Areas/AI与工具/概念/梯度消失与梯度爆炸.md",
    meta: {
      type: "concept",
      status: "seed",
      owner: "mixed",
      summary: "解释梯度消失和梯度爆炸的成因、影响，以及残差连接为什么能缓解深层网络训练问题。",
      tags: ["AI", "深度学习"],
    },
  },
  {
    from: "AI学习/skills/gstack.md",
    to: "30_Areas/AI与工具/工具/gstack.md",
    meta: {
      type: "concept",
      status: "seed",
      owner: "mixed",
      summary: "整理 gstack 这套 Claude Code 工作流技能的定位、角色分工和使用价值。",
      tags: ["AI工具", "工作流"],
    },
  },
  {
    from: "个人提升/收藏整理.md",
    to: "30_Areas/个人成长/资料/收藏整理.md",
    meta: {
      type: "source",
      status: "seed",
      owner: "mixed",
      summary: "保存一条关于 Dan Koe 个人成长视频的来源链接，并关联到后续整理笔记。",
      tags: ["个人成长", "资料"],
    },
  },
  {
    from: "个人提升/用6个月超过99%的人.md",
    to: "30_Areas/个人成长/方法/用6个月超过99%的人.md",
    meta: {
      type: "experience",
      status: "seed",
      owner: "mixed",
      summary: "整理反愿景、抗熵增系统和长期主义这三个个人成长行动框架。",
      tags: ["个人成长", "长期主义"],
    },
  },
  {
    from: "热爱生活🫶/猫猫🐱指南.md",
    to: "30_Areas/生活与关系/经验/猫猫指南.md",
    meta: {
      type: "experience",
      status: "seed",
      owner: "mixed",
      summary: "记录生活照料相关经验，作为生活与关系领域的原始经验沉淀。",
      tags: ["生活", "经验"],
    },
  },
  {
    from: "健身🏋️/头顶上颚.md",
    to: "30_Areas/健康与身体/经验/头顶上颚.md",
    meta: {
      type: "experience",
      status: "seed",
      owner: "mixed",
      summary: "记录头顶上颚相关的身体感受、训练观察或健康经验。",
      tags: ["健康", "身体"],
    },
  },
  {
    from: "健身🏋️/眼球训练.md",
    to: "30_Areas/健康与身体/方法/眼球训练.md",
    meta: {
      type: "concept",
      status: "seed",
      owner: "mixed",
      summary: "整理眼球训练相关方法，方便后续补充动作、频率和复盘效果。",
      tags: ["健康", "训练"],
    },
  },
  {
    from: "健身🏋️/翼状肩胛.md",
    to: "30_Areas/健康与身体/方法/翼状肩胛.md",
    meta: {
      type: "concept",
      status: "seed",
      owner: "mixed",
      summary: "整理翼状肩胛相关知识和训练方法，作为身体改善主题的基础笔记。",
      tags: ["健康", "训练"],
    },
  },
  {
    from: "书影音/cultural consumption list.md",
    to: "30_Areas/输入与审美/书影音/书影音清单.md",
    meta: {
      type: "source",
      status: "seed",
      owner: "mixed",
      summary: "汇总书籍、影视和文化消费记录，作为输入与审美领域的长期清单。",
      tags: ["输入", "审美"],
    },
  },
  {
    from: "TodoList.md",
    to: "10_Inbox/Inbox.md",
    meta: {
      type: "index",
      status: "growing",
      owner: "mixed",
      summary: "作为统一入口，临时收集待办、想法、链接、摘录和等待整理的内容。",
      tags: ["inbox"],
    },
  },
  {
    from: "欢迎.md",
    to: "90_Archive/欢迎.md",
    meta: {
      type: "source",
      status: "archived",
      owner: "llm",
      summary: "Obsidian 默认欢迎笔记，已归档以保持主目录清爽。",
      tags: ["archive"],
    },
  },
];

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
  if (value === undefined || value === null) return "";
  return String(value);
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
    if (rendered.startsWith("\n")) {
      lines.push(`${key}:${rendered}`);
    } else {
      lines.push(`${key}: ${rendered}`);
    }
  }
  lines.push("---", "");
  return lines.join("\n");
}

function hasFrontmatter(content) {
  return content.startsWith("---\n");
}

function addFrontmatter(content, meta) {
  if (hasFrontmatter(content)) return content;
  return frontmatter(meta) + content.trimStart();
}

function writeNote(rel, meta, body) {
  ensureDir(path.dirname(rel));
  fs.writeFileSync(full(rel), frontmatter(meta) + body.trimStart() + "\n", "utf8");
}

function moveNote({ from, to, meta }) {
  const src = full(from);
  const dest = full(to);
  if (!fs.existsSync(src)) {
    if (fs.existsSync(dest)) return;
    throw new Error(`Missing source note: ${from}`);
  }
  ensureDir(path.dirname(to));
  const content = fs.readFileSync(src, "utf8");
  if (fs.existsSync(dest)) {
    throw new Error(`Destination already exists: ${to}`);
  }
  fs.writeFileSync(dest, addFrontmatter(content, meta), "utf8");
  fs.unlinkSync(src);
}

function writeIfMissing(rel, meta, body) {
  if (fs.existsSync(full(rel))) return;
  writeNote(rel, meta, body);
}

function areaIndex(name, subdirs) {
  return `# ${name}

## 领域说明
这里沉淀 ${name} 相关的概念、经验、资料、方法和问题。

## 常用入口
${subdirs.map((dir) => `- [[${dir}/]]`).join("\n")}

## 可复用价值
- 可输出：
- 可行动：
- 可连接：
`;
}

function removeEmptyDirs(dirs) {
  const sorted = [...dirs].sort((a, b) => b.length - a.length);
  for (const rel of sorted) {
    const dir = full(rel);
    if (!fs.existsSync(dir)) continue;
    for (const name of [".DS_Store"]) {
      const systemFile = path.join(dir, name);
      if (fs.existsSync(systemFile)) fs.rmSync(systemFile);
    }
    const entries = fs.readdirSync(dir);
    if (entries.length === 0) fs.rmdirSync(dir);
  }
}

[
  "00_System/templates",
  "10_Inbox/daily",
  "10_Inbox/clips",
  "20_Raw/Articles",
  "20_Raw/Books",
  "20_Raw/Videos",
  "20_Raw/Chats",
  "20_Raw/Screenshots",
  "20_Raw/Personal",
  "40_Projects/Active",
  "40_Projects/Paused",
  "40_Projects/Done",
  "60_Outputs/小红书/草稿",
  "60_Outputs/小红书/已发布",
  "60_Outputs/小红书/复盘",
  "60_Outputs/公众号/草稿",
  "60_Outputs/公众号/已发布",
  "60_Outputs/公众号/复盘",
  "60_Outputs/抖音/脚本",
  "60_Outputs/抖音/已发布",
  "60_Outputs/抖音/复盘",
  "70_Decisions/职业",
  "70_Decisions/副业",
  "70_Decisions/内容定位",
  "70_Decisions/工具选型",
  "70_Decisions/财务消费",
  "70_Decisions/健康生活",
  "70_Decisions/关系合作",
  "90_Archive",
].forEach(ensureDir);

for (const [area, subdirs] of Object.entries(areas)) {
  ensureDir(`30_Areas/${area}`);
  for (const subdir of subdirs) ensureDir(`30_Areas/${area}/${subdir}`);
  writeIfMissing(
    `30_Areas/${area}/_index.md`,
    {
      type: "index",
      status: "growing",
      owner: "mixed",
      summary: `导航 ${area} 领域的核心笔记、资料、方法和可转化输出。`,
      tags: ["area"],
    },
    areaIndex(area, subdirs),
  );
}

writeIfMissing(
  "index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "王木木人生知识库的总入口，连接系统规则、收件箱、领域、项目、输出和决策。",
    tags: ["home"],
  },
  `# 王木木人生知识库

## 快速入口
- [[10_Inbox/Inbox|Inbox]]
- [[00_System/index|System]]
- [[30_Areas/AI与工具/_index|AI与工具]]
- [[30_Areas/职场与工作/_index|职场与工作]]
- [[30_Areas/个人成长/_index|个人成长]]
- [[30_Areas/自媒体与变现/_index|自媒体与变现]]
- [[40_Projects/_index|Projects]]
- [[60_Outputs/_index|Outputs]]
- [[70_Decisions/_index|Decisions]]

## 当前维护协议
- 默认入口：10_Inbox
- 默认 owner：mixed
- 维护频率：每 2-3 天一次
- 输出优先级：小红书、公众号、抖音
`,
);

writeNote(
  "00_System/AGENTS.md",
  {
    type: "index",
    status: "evergreen",
    owner: "user",
    summary: "定义 LLM 维护 Obsidian 人生知识库时必须遵守的权限、结构和写作规则。",
    tags: ["system", "llm"],
  },
  `# AGENTS

## 目标
把这个 Obsidian vault 维护成一个 Life Wiki：既能保存原始资料和个人体验，也能沉淀 AI、职场、个人成长、自媒体变现等长期知识，并持续转化为内容、行动和决策。

## 权限模型
- 默认 \`owner: mixed\`。
- \`owner: user\` 的笔记保留用户原文，LLM 只能追加建议、索引、链接或整理说明。
- \`owner: mixed\` 的笔记可以整理结构、补充 summary、添加链接、移动到合适目录，但必须保留用户原始判断、情绪、经历和决策依据。
- \`owner: llm\` 的笔记可由 LLM 维护、重写、合并和归档。
- \`20_Raw\` 下的原始资料只追加，不覆盖，不删除关键证据。

## 目录职责
- \`10_Inbox\`：默认入口，收集待整理内容。
- \`20_Raw\`：原始资料、重要来源、关键 AI 对话和个人原始记录。
- \`30_Areas\`：长期领域知识，包括 AI、职场、成长、自媒体、写作、财务、健康、生活、输入审美。
- \`40_Projects\`：所有正在推进的事情，按 Active / Paused / Done 管理。
- \`60_Outputs\`：小红书、公众号、抖音等内容产出。
- \`70_Decisions\`：重要选择的背景、选项、标准、决定和复盘。
- \`90_Archive\`：不再活跃但需要保留的内容。

## 笔记字段
每篇维护中的 Markdown 笔记应包含：
\`\`\`yaml
---
type: concept
status: seed
owner: mixed
summary: 一句话说明这篇笔记的核心价值
source:
tags:
---
\`\`\`

## 输出优先级
1. 内容创作：小红书、公众号、抖音
2. 行动决策：项目推进、复盘、选择
3. 学习理解：概念、资料、方法论

## 维护顺序
1. 清理 \`10_Inbox\`
2. 更新 \`30_Areas\` 相关索引与链接
3. 从新增内容提取 \`60_Outputs\` 选题
4. 更新 \`40_Projects\` 状态和下一步
5. 检查 \`70_Decisions\` 是否需要复盘
6. 追加 \`00_System/log.md\`

## 写作要求
- 保留用户口吻中有价值的原始表达。
- 整理时优先做结构化、链接化、可行动化。
- 不把人做成评价档案；涉及他人时记录“我学到了什么”和“我下一步怎么做”。
- 不制造不存在的来源；不确定的内容标为待验证。
`,
);

writeNote(
  "00_System/index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "系统层入口，连接维护协议、模板、日志和 Life Wiki 的结构规则。",
    tags: ["system"],
  },
  `# System

## 规则
- [[AGENTS]]
- [[maintenance-protocol]]
- [[log]]

## 模板
- [[templates/base-note]]
- [[templates/source-note]]
- [[templates/project-note]]
- [[templates/decision-note]]
- [[templates/output-note]]
- [[templates/daily-note]]
`,
);

writeIfMissing(
  "00_System/log.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "记录知识库结构调整、维护动作和重要整理结果。",
    tags: ["system", "log"],
  },
  `# 维护日志

## ${today}
- 建立 Life Wiki 结构。
- 迁移现有笔记到 10_Inbox、30_Areas、90_Archive。
- 增加轻量 YAML 字段：type/status/owner/summary/source/tags。
`,
);

writeNote(
  "00_System/maintenance-protocol.md",
  {
    type: "index",
    status: "evergreen",
    owner: "mixed",
    summary: "定义每 2-3 天维护知识库时的固定顺序、检查项和输出结果。",
    tags: ["system", "maintenance"],
  },
  `# 维护协议

## 频率
每 2-3 天执行一次，优先周一、周三、周五。

## 执行顺序
1. 清理 \`10_Inbox\`
2. 更新 \`30_Areas\` 相关索引与笔记链接
3. 从新增内容提取 \`60_Outputs\` 选题
4. 更新 \`40_Projects\` 状态和下一步
5. 检查 \`70_Decisions\` 是否需要复盘
6. 追加 \`00_System/log.md\`

## 每次维护产物
- Inbox 处理记录
- 新增或更新的领域笔记
- 本轮输出选题
- 项目下一步
- 需要复盘的决策
`,
);

writeIfMissing(
  "20_Raw/_index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "索引原始资料层，用于保存重要来源、关键对话、截图、个人原始记录和资料证据。",
    tags: ["raw"],
  },
  `# Raw

## 保存规则
- 普通资料：链接 + 一句话摘要
- 重要资料：原文/PDF/截图 + source note
- AI 对话：只保存关键对话
- 个人记录：完整保存，默认 owner: user
`,
);

writeIfMissing(
  "40_Projects/_index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "管理所有正在推进、暂停和已完成的人生项目。",
    tags: ["projects"],
  },
  `# Projects

## 状态
- [[Active/]]
- [[Paused/]]
- [[Done/]]

## 判断规则
- 有明确推进动作：放 Projects
- 只是长期关注：放 Areas
- 只是资料参考：放 Raw 或 Areas/资料
- 已形成内容：放 Outputs
- 重大选择过程：放 Decisions
`,
);

writeIfMissing(
  "60_Outputs/_index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "管理小红书、公众号和抖音的选题池、草稿、已发布内容与复盘。",
    tags: ["outputs"],
  },
  `# Outputs

## 平台
- [[小红书/选题池]]
- [[公众号/选题池]]
- [[抖音/选题池]]

## 转化规则
每篇重要笔记都检查：
- 可输出：
- 可行动：
- 可连接：
`,
);

for (const platform of ["小红书", "公众号", "抖音"]) {
  writeIfMissing(
    `60_Outputs/${platform}/选题池.md`,
    {
      type: "index",
      status: "growing",
      owner: "mixed",
      summary: `${platform} 内容选题池，用于从知识库笔记转化内容创意。`,
      tags: ["output", platform],
    },
    `# ${platform}选题池

## 待选题

## 已进入草稿

## 已发布复盘
`,
  );
}

writeIfMissing(
  "70_Decisions/_index.md",
  {
    type: "index",
    status: "growing",
    owner: "mixed",
    summary: "记录重要选择的背景、选项、判断标准、当前决定和复盘结果。",
    tags: ["decisions"],
  },
  `# Decisions

## 类别
- [[职业/]]
- [[副业/]]
- [[内容定位/]]
- [[工具选型/]]
- [[财务消费/]]
- [[健康生活/]]
- [[关系合作/]]
`,
);

const templates = {
  "base-note": `# 标题

## 核心内容

## 我的理解

## 可复用价值
- 可输出：
- 可行动：
- 可连接：
`,
  "source-note": `# 资料标题

## 原始来源

## 为什么保存

## 关键摘录

## 我的初步理解

## 可转化方向
- 可输出：
- 可行动：
- 可连接：
`,
  "project-note": `# 项目名

## 目标

## 为什么重要

## 当前状态

## 下一步

## 相关笔记

## 复盘
`,
  "decision-note": `# 决策标题

## 背景

## 选项

## 判断标准

## 当前决定

## 预期结果

## 复盘日期

## 复盘结果
`,
  "output-note": `# 内容标题

## 来源笔记

## 核心观点

## 小红书版本

## 公众号版本

## 抖音脚本

## 发布复盘
`,
  "daily-note": `# {{date}}

## 今天记录

## 观察与感受

## 输入

## 下一步

## 可沉淀
- 可输出：
- 可行动：
- 可连接：
`,
};

for (const [name, body] of Object.entries(templates)) {
  writeNote(
    `00_System/templates/${name}.md`,
    {
      type: "source",
      status: "evergreen",
      owner: "llm",
      summary: `${name} 模板，用于快速创建结构一致的 Life Wiki 笔记。`,
      tags: ["template"],
    },
    body,
  );
}

for (const migration of migrations) moveNote(migration);

removeEmptyDirs([
  "00_Inbox",
  "01_Projects/个人机器人",
  "01_Projects",
  "02_Areas/健康",
  "02_Areas/财务",
  "02_Areas/AI",
  "02_Areas/工作",
  "02_Areas/个人成长",
  "02_Areas",
  "03_Resources/书籍",
  "03_Resources/文章",
  "03_Resources/教程",
  "03_Resources/工具",
  "03_Resources",
  "04_Archive",
  "AI学习/基础知识",
  "AI学习/skills",
  "AI学习",
  "个人提升",
  "热爱生活🫶",
  "健身🏋️",
  "书影音",
]);

console.log("Life Wiki migration complete.");
