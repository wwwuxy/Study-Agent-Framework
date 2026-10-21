import json

from app.providers.base import TextOnlyAdapter


class FakeAdapter(TextOnlyAdapter):
    """Explicit offline demonstration data. Never selected as a network fallback."""

    def __init__(self):
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "cost": 0,
            "cost_status": "demo_no_charge",
            "currency": "USD",
            "usage_reported": True,
        }

    async def probe_capabilities(self):
        return {
            "chat": True,
            "structured_json": True,
            "file_input": False,
            "embedding": False,
            "web_search": False,
            "supported_mime_types": [],
            "adapter": "fake",
            "is_demo": True,
        }

    async def generate_text(self, messages):
        return "离线演示内容，不代表真实模型调用。"

    async def generate_structured(self, messages, schema):
        task = json.loads(messages[-1]["content"])
        title = schema.get("title")
        if title == "AnalysisContent":
            return {
                "summary": "离线固定演示：先完成当前可执行任务，再根据真实作答调整安排。",
                "recommendations": ["优先继续尚未完成的课堂", "按今日预算安排到期复习"],
                "caveats": ["这是固定演示，不代表真实模型分析或教育效果。"],
            }
        if title == "ChatDecision":
            import re

            message = task.get("message", "")
            patch = {}
            additions = []
            stages = None
            match = re.search(r"(\d+)\s*分钟", message)
            if match:
                patch["daily_minutes"] = int(match.group(1))
            if "面试" in message:
                patch["teaching_preferences"] = "使用贴近面试的例子，简洁解释后再练习"
            if "先学" in message and "进程" in message:
                patch["priority_concept_ids"] = ["process"]
            if "虚拟内存" in message and any(w in message for w in ["增加", "补充", "添加"]):
                additions = [
                    {
                        "key": "virtual_memory",
                        "name": "虚拟内存",
                        "module": "内存管理",
                        "objectives": ["解释地址映射"],
                        "prerequisites": ["os"],
                        "importance": 3,
                        "minutes": 15,
                    }
                ]
                patch["priority_concept_ids"] = ["virtual_memory"]
            if patch or additions:
                known = {c["key"]: c for c in [*task.get("concepts", []), *additions]}
                if not task.get("intent", {}).get("stages") or additions or "先学" in message:
                    ordered = []
                    remaining = dict(known)
                    while remaining:
                        ready = [
                            c
                            for c in remaining.values()
                            if all(p in {n["key"] for n in ordered} for p in c["prerequisites"])
                        ]
                        if not ready:
                            break
                        for node in ready:
                            ordered.append(node)
                            remaining.pop(node["key"])
                    stages = [
                        {
                            "title": c["name"],
                            "objective": "；".join(c["objectives"]),
                            "concept_ids": [c["key"]],
                            "suggested_sessions": 2,
                        }
                        for c in ordered
                    ][:12]
                return {
                    "kind": "update_plan",
                    "reply": "离线固定演示：已提出你的学习安排调整，具体生效结果见下方。",
                    "patch": patch,
                    "added_concepts": additions,
                    "stages": stages,
                    "interrupt_current": "先学" in message or bool(additions),
                    "reason": "用户明确调整学习需求",
                }
            if "调整" in message:
                return {
                    "kind": "clarify",
                    "reply": "你希望调整每天学习时间，还是优先学习的知识点？（固定演示）",
                }
            return {
                "kind": "reply",
                "reply": "当前计划结合知识前置、作答证据和复习到期安排。你可以告诉我新的时间或重点。（固定演示）",
            }
        if title == "Curriculum":
            return {
                "concepts": [
                    {
                        "key": "os",
                        "name": "操作系统的职责",
                        "module": "操作系统基础",
                        "objectives": ["区分资源管理与应用功能"],
                        "prerequisites": [],
                        "importance": 3,
                        "minutes": 15,
                    },
                    {
                        "key": "process",
                        "name": "进程与调度",
                        "module": "进程管理",
                        "objectives": ["解释进程与 CPU 调度"],
                        "prerequisites": ["os"],
                        "importance": 2,
                        "minutes": 20,
                    },
                    {
                        "key": "deadlock",
                        "name": "死锁必要条件",
                        "module": "进程管理",
                        "objectives": ["识别循环等待"],
                        "prerequisites": ["process"],
                        "importance": 1,
                        "minutes": 20,
                    },
                ]
            }
        if title == "QuestionBatch":
            return {
                "items": [
                    self.question(key, i)
                    for i, key in enumerate(["os", "process", "deadlock", "process", "deadlock"])
                ]
            }
        if title == "LessonContent":
            key = task["concept_ids"][0]
            count = task.get("existing_question_count", 0)
            details = {
                "virtual_memory": (
                    "理解虚拟内存",
                    "虚拟内存为进程提供独立的虚拟地址空间，系统通过页表将虚拟页映射到物理页。此内容是固定演示。",
                    "例如两个进程使用相同的虚拟地址，经过各自的页表后可访问不同的物理内存。",
                ),
                "os": (
                    "理解操作系统",
                    "操作系统管理 CPU、内存和设备，向应用程序提供受控的系统调用接口。阅读本讲只记录经历，掌握需要独立测评证据。",
                    "例如保存文件时，应用经系统调用请求文件系统写入磁盘。",
                ),
                "process": (
                    "理解进程与调度",
                    "进程是执行中的程序及其资源。调度器选择就绪进程获得 CPU；等待 I/O 的进程会进入阻塞状态。",
                    "例如浏览器与编辑器通过时间片交替使用同一个 CPU 核。",
                ),
                "deadlock": (
                    "识别死锁",
                    "死锁需同时满足互斥、占有并等待、不可剥夺、循环等待四个必要条件。打破任一条件可预防死锁。",
                    "例如甲持有打印机等待扫描仪，而乙持有扫描仪等待打印机。",
                ),
            }
            heading, explanation, example = details[key]
            return {
                "title": heading,
                "explanation": explanation,
                "example": example,
                "exercises": [self.question(key, count)],
            }
        if title == "Hint":
            return {"hint": "回忆该概念的定义，并逐个排除与定义不符的选项。使用提示会作为辅助证据记录。"}
        if title == "Grade":
            return {
                "is_correct": None,
                "confidence": "low",
                "feedback": "离线演示不评估开放回答，请连接真实模型。",
                "misconceptions": [],
            }
        raise ValueError("Unsupported demo schema")

    @staticmethod
    def question(key, index):
        bank = {
            "virtual_memory": [
                ("虚拟内存为进程提供什么？", "独立的虚拟地址空间", "无限数量的 CPU 寄存器"),
                ("虚拟地址通常通过什么映射到物理地址？", "页表与地址转换机制", "文件名排序"),
                ("两个进程使用相同虚拟地址，是否必须访问同一物理页？", "不必须，各自页表可以不同", "必须"),
            ],
            "os": [
                ("哪项属于操作系统的核心职责？", "管理 CPU、内存和设备", "撰写用户文章"),
                ("多个应用同时请求内存时，由谁协调分配？", "操作系统", "图片编辑器"),
                ("应用要访问受保护设备，通常通过什么接口？", "系统调用", "直接改写所有硬件寄存器"),
                ("某程序持续占用 CPU，系统如何让其他程序继续运行？", "调度与时间片", "删除其他程序的数据"),
            ],
            "process": [
                ("什么是进程？", "执行中的程序及其资源", "硬盘上静态的文本"),
                ("哪个组件选择就绪进程获得 CPU？", "调度器", "文本编辑器"),
                ("进程等待磁盘 I/O 时通常处于什么状态？", "阻塞", "一直执行指令"),
                ("时间片用完后仍可执行的进程通常转入？", "就绪队列", "永久删除状态"),
                ("两个进程能否在单核 CPU 上通过调度交替前进？", "可以", "绝对不可以"),
                ("进程切换时需要保存什么？", "执行上下文", "只需保存应用名称"),
            ],
            "deadlock": [
                ("哪项是死锁的必要条件？", "循环等待", "无限内存"),
                ("打破循环等待能否预防死锁？", "能", "不能"),
                ("甲持有资源 X 等待 Y，乙持有 Y 等待 X，出现了什么？", "循环等待", "文件压缩"),
                ("对所有锁按统一顺序申请，主要打破哪项条件？", "循环等待", "资源互斥"),
                ("持有资源同时申请其他资源对应哪个条件？", "占有并等待", "无资源占用"),
                ("允许系统强制回收已分配资源，打破哪个条件？", "不可剥夺", "所有条件都没有改变"),
            ],
        }
        prompt, a, b = bank[key][index % len(bank[key])]
        return {
            "prompt": prompt,
            "concept_keys": [key],
            "kind": "choice",
            "options": {"A": a, "B": b},
            "answer": "A",
            "rubric": f"应能解释：{a}。",
            "difficulty": 2,
        }
