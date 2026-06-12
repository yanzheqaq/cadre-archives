# New methods to insert into inventory_entry_dialog.py
# Insert after line 4561 (after context_menu method, before _check_can_move_selected)

    # ------------------------------------------------------------------
    # 跨类别迁移：将选中的目录条目上移/下移至相邻类别
    # ------------------------------------------------------------------
    def _get_parent_category_id(self, item):
        """获取 item 所属的类别（根级父节点）的 template_item_id。
        如果 item 本身是根级节点则返回它自己的 id；
        如果 item 是根级节点的子孙则返回最顶层根级节点的 id。"""
        if not item:
            return None
        parent = item.parent()
        if parent is None or parent == self.catalog_tree.invisibleRootItem():
            return item.data(0, Qt.UserRole)
        # 向上追溯到最顶层的非根父节点（即类别节点）
        prev = None
        while parent and parent != self.catalog_tree.invisibleRootItem():
            grandparent = parent.parent()
            if grandparent is None or grandparent == self.catalog_tree.invisibleRootItem():
                return parent.data(0, Qt.UserRole)
            parent = grandparent
        return None

    def _get_adjacent_category_names(self, items):
        """获取选中条目当前类别的上一个和下一个兄弟类别的名称。
        Returns (prev_cat_name, next_cat_name)，无相邻方向时为 None。"""
        if not items:
            return (None, None)
        current_cat_id = self._get_parent_category_id(items[0])
        if not current_cat_id:
            return (None, None)
        root = self.catalog_tree.invisibleRootItem()
        cat_idx = None
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.UserRole) == current_cat_id:
                cat_idx = i
                break
        if cat_idx is None:
            return (None, None)
        prev_name = None
        next_name = None
        if cat_idx > 0:
            prev_child = root.child(cat_idx - 1)
            prev_name = (prev_child.data(1, Qt.UserRole + 10) or prev_child.text(1) or "").strip()
            if not prev_name:
                prev_name = prev_child.text(0).strip() or "未命名类别"
        if cat_idx < root.childCount() - 1:
            next_child = root.child(cat_idx + 1)
            next_name = (next_child.data(1, Qt.UserRole + 10) or next_child.text(1) or "").strip()
            if not next_name:
                next_name = next_child.text(0).strip() or "未命名类别"
        return (prev_name, next_name)

    def _check_can_cross_category_move(self, items):
        """检查选中的条目是否可以进行跨类别迁移。
        条件：1) 所有选中项属于同一类别  2) 该类别有相邻的兄弟类别
        Returns (can_move, prev_cat_id, next_cat_id)"""
        if not items:
            return (False, None, None)
        first_cat_id = self._get_parent_category_id(items[0])
        if not first_cat_id:
            return (False, None, None)
        for item in items:
            if self._get_parent_category_id(item) != first_cat_id:
                return (False, None, None)
        root = self.catalog_tree.invisibleRootItem()
        cat_idx = None
        for i in range(root.childCount()):
            if root.child(i).data(0, Qt.UserRole) == first_cat_id:
                cat_idx = i
                break
        if cat_idx is None:
            return (False, None, None)
        prev_cat_id = root.child(cat_idx - 1).data(0, Qt.UserRole) if cat_idx > 0 else None
        next_cat_id = root.child(cat_idx + 1).data(0, Qt.UserRole) if cat_idx < root.childCount() - 1 else None
        can_move = prev_cat_id is not None or next_cat_id is not None
        return (can_move, prev_cat_id, next_cat_id)

    def _on_move_to_prev_category(self):
        """将选中的条目迁移到上一个类别"""
        self._cross_category_move(-1)

    def _on_move_to_next_category(self):
        """将选中的条目迁移到下一个类别"""
        self._cross_category_move(1)

    def _cross_category_move(self, direction):
        """跨类别迁移：direction=-1 上移至上一个类别, 1 下移至下一个类别。
        迁移后条目出现在目标类别的最后，然后刷新树并更新序号。"""
        selected_items = self.catalog_tree.selectedItems()
        if not selected_items:
            StyledMessageBox.information(self, "提示", "请先选择要迁移的条目", self.current_theme)
            return
        can_move, prev_cat_id, next_cat_id = self._check_can_cross_category_move(selected_items)
        if not can_move:
            StyledMessageBox.warning(self, "提示", "选中的条目无法跨类别迁移（类别不确定或无相邻类别）", self.current_theme)
            return
        target_cat_id = prev_cat_id if direction < 0 else next_cat_id
        if not target_cat_id:
            return
        # 获取目标类别名称
        root = self.catalog_tree.invisibleRootItem()
        target_name = ""
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, Qt.UserRole) == target_cat_id:
                target_name = (child.data(1, Qt.UserRole + 10) or child.text(1) or child.text(0) or "").strip()
                break
        if not target_name:
            target_name = "未命名类别"
        count = len(selected_items)
        msg = "确定将选中的 {} 个条目迁移到【{}】吗？\n\n迁移后条目将出现在目标类别的最后。".format(count, target_name)
        if StyledMessageBox.question(self, "确认迁移", msg,
                                     StyledMessageBox.Yes | StyledMessageBox.No,
                                     StyledMessageBox.No, self.current_theme) != StyledMessageBox.Yes:
            return
        # 收集所有选中条目的 template_item_id（包括子节点）
        all_ids = []
        for item in selected_items:
            ids = self._collect_tpl_ids(item)
            all_ids.extend(ids)
        all_ids = list(set(all_ids))  # 去重
        if not all_ids:
            return
        # 调用 repo 层迁移
        try:
            from common.repositories.template_repo import move_catalog_template_items_to_parent
            updated = move_catalog_template_items_to_parent(
                template_item_ids=all_ids,
                new_parent_id=int(target_cat_id),
            )
            print("[catalog-entry] cross-category move: {} items to parent_id={}".format(updated, target_cat_id))
        except Exception as e:
            print("[catalog-entry] cross-category move failed: {}".format(e))
            StyledMessageBox.warning(self, "提示", "跨类别迁移失败：{}".format(e), self.current_theme)
            return
        # 刷新整个目录树
        self._populate_catalog_tree()