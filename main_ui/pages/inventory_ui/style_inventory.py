class InventoryReceiveStyle:
    LIGHT_STYLE = """
        #section_title {
            font-weight: bold; font-size: 14px; color: #374151; padding: 5px;
        }

        #tab_btn {
            background-color: transparent;
            color: #374151;
            border: none;
            padding: 4px 12px;
            font-size: 13px;
            font-weight: bold;
            border-bottom: 2px solid transparent;
        }
        #tab_btn:hover {
            color: #10b981;
            background-color: #f0fdf4;
        }
        #tab_btn:checked {
            color: #10b981;
            border-bottom: 2px solid #10b981;
        }

        #func_btn_add, #func_btn_delete, #func_btn_sort, #func_btn_return, #func_btn_transfer,
        #right_func_btn {
            border: 1px solid #e5e7eb;
            background-color: #ffffff;
            border-radius: 6px;
            padding: 4px;
        }
        #func_btn_add:hover, #func_btn_delete:hover, #func_btn_sort:hover, #func_btn_return:hover, #func_btn_transfer:hover,
        #right_func_btn:hover {
            background-color: #f8fafc;
            border-color: #cbd5f5;
        }

        QSplitter::handle { background-color: #e5e7eb; }

        QListWidget { border: 1px solid #d1d5db; border-radius: 4px; background-color: #ffffff; outline: none; }
        QListWidget::item { height: 40px; padding-left: 10px; border-bottom: 1px solid #f3f4f6; color: #374151; }
        QListWidget::item:selected { background-color: #eff6ff; color: #1e40af; border-left: 3px solid #1e40af; }
        QListWidget::item:hover { background-color: #f9fafb; }

        QTableWidget { border: 1px solid #d1d5db; border-radius: 4px; background-color: white; gridline-color: #f3f4f6; color: #374151; }
        QHeaderView::section { background-color: #f9fafb; padding: 8px; border: none; border-bottom: 1px solid #d1d5db; font-weight: bold; color: #374151; }
        QTableWidget::item { padding: 5px; }
        QTableWidget::item:selected { background-color: #e0e7ff; color: #1e3a8a; }

        /* 机构树样式（移除可能覆盖指示器的样式，使用默认展开/收缩符号） */
        QTreeWidget { border: 1px solid #d1d5db; border-radius: 4px; background-color: #ffffff; }
        QTreeWidget::item { padding: 6px 8px; color: #374151; }
        QTreeWidget::item:selected { background-color: #e0e7ff; color: #1e3a8a; }
        QTreeWidget::item:hover { background-color: #f9fafb; }
    """

    DARK_STYLE = """
        #section_title {
            font-weight: bold; font-size: 14px; color: #d1d5db; padding: 5px;
        }

        #tab_btn {
            background-color: transparent;
            color: #d1d5db;
            border: none;
            padding: 4px 12px;
            font-size: 13px;
            font-weight: bold;
            border-bottom: 2px solid transparent;
        }
        #tab_btn:hover {
            color: #10b981;
            background-color: #064e3b;
        }
        #tab_btn:checked {
            color: #10b981;
            border-bottom: 2px solid #10b981;
        }

        #func_btn_add, #func_btn_delete, #func_btn_sort, #func_btn_return, #func_btn_transfer,
        #right_func_btn {
            border: 1px solid #374151;
            background-color: #111827;
            border-radius: 6px;
            padding: 4px;
        }
        #func_btn_add:hover, #func_btn_delete:hover, #func_btn_sort:hover, #func_btn_return:hover, #func_btn_transfer:hover,
        #right_func_btn:hover {
            background-color: #1f2937;
            border-color: #4b5563;
        }

        QSplitter::handle { background-color: #4b5563; }

        QListWidget { border: 1px solid #4b5563; border-radius: 4px; background-color: #1f2937; outline: none; alternate-background-color: #374151; }
        QListWidget::item { height: 40px; padding-left: 10px; border-bottom: 1px solid #374151; color: #d1d5db; }
        QListWidget::item:selected { background-color: #1e3a8a; color: #ffffff; border-left: 3px solid #60a5fa; }
        QListWidget::item:hover { background-color: #374151; }

        QTableWidget { border: 1px solid #4b5563; border-radius: 4px; background-color: #1f2937; gridline-color: #374151; color: #d1d5db; alternate-background-color: #374151; }
        QHeaderView::section { background-color: #111827; padding: 8px; border: none; border-bottom: 1px solid #4b5563; font-weight: bold; color: #d1d5db; }
        QTableWidget::item { padding: 5px; }
        QTableWidget::item:selected { background-color: #1e3a8a; color: #ffffff; }

        /* 机构树样式（移除可能覆盖指示器的样式，使用默认展开/收缩符号） */
        QTreeWidget { border: 1px solid #374151; border-radius: 4px; background-color: #1f2937; }
        QTreeWidget::item { padding: 6px 8px; color: #d1d5db; }
        QTreeWidget::item:selected { background-color: #1e3a8a; color: #ffffff; }
        QTreeWidget::item:hover { background-color: #2b3544; }
    """

    # 兼容调用别名
    light = LIGHT_STYLE
    dark = DARK_STYLE

