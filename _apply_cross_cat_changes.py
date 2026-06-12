# -*- coding: utf-8 -*-
"""Apply cross-category migration changes to inventory_entry_dialog.py"""

dialog_path = r"main_ui/pages/inventory_ui/inventory_entry_dialog.py"

with open(dialog_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# ----- 1) Modify context_menu: insert cross-category section -----
# Find the two lines between which we want to insert:
# Line 4550: "        menu.addSeparator()" (the separator before delete)
# Line 4551: "        "
# Line 4552: "        # 删除"

# We'll replace the block from "        menu.addSeparator()\n        \n        # 删除"
# (the second separator) with separator + cross-cat + separator + delete

insert_lines = [
    "        menu.addSeparator()\n",
    "\n",
    "        # 跨类别迁移\n",
    "        can_cross, prev_cat_id, next_cat_id = self._check_can_cross_category_move(selected_items)\n",
    "        if can_cross:\n",
    "            prev_cat_name, next_cat_name = self._get_adjacent_category_names(selected_items)\n",
    "            if prev_cat_name:\n",
    "                label = \"上移至 \" + prev_cat_name + (\" (\" + str(len(selected_items)) + \"项)\" if len(selected_items) > 1 else \"\")\n",
    "                action_move_to_prev = menu.addAction(label)\n",
    "                action_move_to_prev.triggered.connect(self._on_move_to_prev_category)\n",
    "            if next_cat_name:\n",
    "                label = \"下移至 \" + next_cat_name + (\" (\" + str(len(selected_items)) + \"项)\" if len(selected_items) > 1 else \"\")\n",
    "                action_move_to_next = menu.addAction(label)\n",
    "                action_move_to_next.triggered.connect(self._on_move_to_next_category)\n",
    "            if prev_cat_name or next_cat_name:\n",
    "                menu.addSeparator()\n",
    "        \n",
    "        # 删除\n",
]

# Find the line number of "        menu.addSeparator()" that appears right before "# 删除"
# in the context_menu method. This is the second menu.addSeparator() in the method.
# We'll find it by looking for the pattern: menu.addSeparator() followed by blank line then # 删除

target_found = False
for i in range(4517, min(len(lines), 4565)):
    if (lines[i].strip() == "menu.addSeparator()" and
        i + 2 < len(lines) and
        "删除" in lines[i + 2]):
        # This is the separator before delete. Replace from the blank line before it.
        # We want to replace lines[i-1] (blank), lines[i] (separator), lines[i+1] (blank),
        # lines[i+2] (# 删除) with our insert_lines
        # Actually let's just replace lines[i] through lines[i+2] with our block
        lines[i:i+3] = insert_lines
        target_found = True
        print(f"Replaced context_menu cross-cat section at line {i+1}")
        break

if not target_found:
    print("WARNING: Could not find target location for context_menu modification")
    # Fallback: search more broadly
    for i in range(4517, min(len(lines), 4565)):
        if lines[i].strip() == "menu.addSeparator()" and i > 4530:
            # Check if next non-blank line contains "删除"
            for j in range(i+1, min(i+5, len(lines))):
                if "删除" in lines[j]:
                    lines[i:i+3] = insert_lines
                    target_found = True
                    print(f"Fallback: Replaced at line {i+1}")
                    break
            if target_found:
                break

# ----- 2) Insert helper methods after context_menu (after line 4561, before _check_can_move_selected) -----
# Read the new methods from _cross_cat_methods.py
with open("_cross_cat_methods.py", "r", encoding="utf-8") as f:
    helper_code = f.read()

# Find the line "    def _check_can_move_selected(self, items):" 
# Note: line numbers have shifted if we inserted earlier
inserted_at = None
for i, line in enumerate(lines):
    if "def _check_can_move_selected(self, items):" in line:
        # Insert before this line
        # Add a blank line between methods for readability
        lines.insert(i, helper_code + "\n")
        inserted_at = i + 1
        print(f"Inserted helper methods before line {inserted_at}")
        break

if inserted_at is None:
    print("WARNING: Could not find _check_can_move_selected method")
else:
    # Write back
    with open(dialog_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Successfully wrote {dialog_path}")