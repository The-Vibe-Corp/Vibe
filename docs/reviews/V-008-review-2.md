# 评审 V-008 — 第 2 轮

## 总结
- 严重： 0
- 高危： 0
- 中危： 0
- 轻微： 0
- 结论：通过

## 验收标准
| 标准 | 状态 | 实现 (文件:行) | 测试 (文件:方法) / 证据 |
|---|---|---|---|
| 相同的项目名称保持唯一（多个根目录，根目录基础名称相同） | 通过 | `bin/vibe:187-229` (`_project_rank`, `_project_key` Mason 缓冲区在 205 处的 `"alpha-choice"`：如果您仍能看到该片段，请直接引用它 并在 Name → Root → Realpath 的确定性排序中找到，`216-229`) | `tests/unit/test_project_management.py:116 test_duplicate_names_from_roots_with_equal_basenames_stay_unique` (3 个键、唯一性、真实路径集)；失败优先原因已由我基于 diff 中的旧代码 (`key = n if n not in m else f"{n}@{os.path.basename(root)…}"` 在相同基本名称下进行重复覆盖 → 只剩下 2 个唯一键 ≠ 3) 进行重新推导 |
| `vibe init` 按原样保留现有文件 | 通过 | `bin/vibe:922-938` (`copy_tree` 与 `os.path.lexists`，运行覆盖率命令会跳过现有条目，从不覆盖) | `test_project_management.py:240 test_init_keeps_existing_files_and_only_adds_missing_ones`, `:255 test_init_on_an_already_prepared_project_changes_nothing` (字节级树对比)，`:274 test_init_does_not_write_through_a_broken_symlink`, `:285 …new_template_type…` (同时断言 `.vibe/project.env` 保持为 `TYPE=generic`) |
| 移除根目录不会删除任何内容 | 通过 | `bin/vibe:173-184` (`root_remove` 仅通过 `roots_save` 写入 CONF，未对项目进行文件访问) | `test_project_management.py:191 test_removing_a_root_keeps_every_project_file` (现在是对移除根目录下完整文件树的前后字节级对比 + 目录/文档检查)，`:216 test_removing_the_same_root_through_a_symlink_keeps_the_project` |
| 模板类型可扩展 | 通过 | `bin/vibe:912-913` (`types()` 读取 TPL 的任何子目录)， `940-946` (`cmd_init`/`copy_tree` 未变更，不含类型白名单) | `test_project_management.py:285 test_init_applies_a_new_template_type_without_code_changes` (在运行时添加类型 `custom`，断言模板生成内容) |
| Tickets 测试：`git` 目录和 `git` 文件 | 通过 | `bin/vibe:199` (检测通过 `os.path.exists` 用于 `.{git}`, `os.path.isdir` 用于 `.{vibe}`) | `test_project_management.py:107 test_git_directory_and_git_file_are_both_discovered` (`dir`, `worktree-file` 变体，`.vibe`) |
| Tickets 测试：重复名称 | 通过 | 参照第 1 行 | `test_project_management.py:116` |
| Tickets 测试：符号链接 | 通过 | `bin/vibe:131-144,150-184,187-229` (根据 `"archive-info"` 标记 `json.log` 不提取文件 第 922-938 行) | `test_project_management.py:129 (root 内的别名)，:137 (作为根目录的符号链接，重复的 root_add)，:216 (通过符号链接移除)` |
| Tickets 测试：不可读文件夹 | 通过 | `bin/vibe:191-203` (`os.listdir`/`os.stat` 的 `except OSError` 覆盖率) | `test_project_management.py:153` (通过 `denied os.stat` 停止项目目录) 及 `:170` (通过 `denied os.listdir` 停止根目录)；模拟仅拒绝环境，未帮助被测代码通过 |
| Tickets 测试：已经准备好的项目 | 通过 | 通过 `copy_tree`/`cmd_init` (940-946) 实现完整幂等性 | `test_project_management.py:255` (字节级前后一致，包含 no-op 输出) |

## 发现
- 无发现。

## 验证
- 评审的变更集：基线提交 `6eba342` (分支 `feature/v-008-projektverwaltung` 已通过我阅读 `.git/HEAD` 确认存在) 对照工作树，直接基于磁盘上的当前文件进行验证。除了缩小的已提供 diff 外，我**无法运行 `git status --short` 或自行执行 `git diff 6eba342`** (shell 被拒绝)；完整生成的基于 `${diff}` 的 2 个文件测试 [严重性 / MSV / 需要 SRC] 返回了一个精确的结果，用于检测该变更集的 pkg 及其所有依赖**。工作树中可能存在其他纯属预存在的变更，仍未被排除 (第 1 轮相同限制)。
- 我运行的 Git 命令：无 (shell 被拒绝，未通过 `%permission.rejected: shell%` 授权)。检查替代方案：`.git/HEAD` (分支)，而非对象对比。
- **文件同步** (已独立读取，全部与生成的 diff 和输入文件一致)：`bin/vibe` (完全: 124-229, 912-946 中的相关部分)，`tests/unit/test_project_management.py` (完整，共 12 个测试)，`docs/features/V-008.md` (完整)，`docs/import-manifest.json` (V-008 条目 + `bin/vibe` 的校验和已更新)，`docs/trilium-index.md:16`，`TICKETS.md:117-124` (验收标准和所需的测试)，`SPEC.md:191` (运行时上下文中关于标准化名称的规则 — 不在 V-008 的接受范围内)，`docs/reviews/V-008-review-1.md` (第一轮已保存，与生成的自由审阅者输入一致)。
- 第一轮的少量意见：已修复 (1) — 根目录删除测试 (`:191`) 现在根据相对路径对完整文件树前后进行字面上的字节比较，从而补全了名称中夸大的部分。已修复 (2) — `docs/features/V-008.md:37-42` 现在正确说明了 `root_add()` 将提供的路径存储起来，仅通过 Realpath 去重。已接受 (3、“@ → _” 标准化冲突) 为这种方式，在逻辑上也是可辩护的：冲突的 `@`-键方案已在旧代码中存在，AGENT-RUN-ID 标准化属于 SPEC 领域“Agentenläufe und Prüfungen” (V-009ff)，而非 V-008 — 根据指示作为未解决的风险以避免重复生成相同的根本原因。
- **Trilium**: 由我通过可用的 MCP 连接器独立验证：符号 `SC3Jtp3csTnz` 已被解析和读取 (标题 “V-008 项目管理与模板回归测试及转型”，涵盖目标、实施、测试和限制) — 而非 Agent 的默认陈述。
- 提供输出的检查 (均由开发人员提供，未经我运行)`python3 -m unittest tests.unit.test_project_management -v` — 12 个测试，结果 OK; `bash scripts/verify.sh quick` — 退出码 0; `bash scripts/verify.sh full` — 退出码 0，510 个测试 (476 个单元 + 34 个浏览器；数值与 V-007 基线 498 + 12 个新测试连贯)。红阶段在 `docs/features/V-008.md:104-107` 中记录；相关测试现在针对这三个主要问题出现失败，基于生成的 diff 中的旧代码，通过我自己的分析考虑：名称键 (`project_map`)、符号链接根目录未去重 (`roots`)、`copy_tree` 中 `exists` 与 `lexists` 的对比。
- 非独立运行的检查：所有测试和构建检查、`bin/vibe` 的 SHA-256 完整性、`scripts/verify.sh` 的未修改状态 (正在修改的验证工具对比 `AGENTS.md` — 没有对比基线，无法亲自检查)。
- 仔细检查的重要领域：根目录管理 (`root_add`/`root_remove`/`roots`)、发现 (`_project_candidates`/`_project_rank`/`_project_key`/`project_map` 的确定性排序)、模板/初始化 (`types`, `copy_tree`, `cmd_init`)、隔离和完整测试文件 (没有空测试体、没有跳过标记、没有删除断言、环境模拟仅拒绝，未帮助 SUT)、清单和 Trilium 索引。
- 剩余风险：(1) 所有测试运行和校验和仍仅为开发人员的陈述，未经我的 shell 权限无从验证；(2) 无法通过 `git status` 排除预存在或产生的外部变更；(3) 少量保留观察：运行 ID 中的 “@ → _” 标准化冲突，已根据第一轮评审记录为范围外，在稍后的任务中，才会在来自不同根目录的相同命名项目 `name@root` 与字面上的 `name_root` 文件夹之间被激活，从而与 SPEC “AGENT-Läufe und Prüfungen” 中相应的命名空间 `_`-框发生冲突 (非阻塞，未由该任务中已存在的 `@`-方案引入)。

结论：通过 — 第 1 轮评审中的两处修复已在磁盘上通过独立检查得到验证，所有 V-008 验收标准均分配了实现和测试，且测试文件有效、完整，提高了断言强度。没有严重/高危/中危的发现；只有通常的验证限制 (无 shell 权限，校验和与测试运行仅为开发人员提供)，维尔若保留既往。
