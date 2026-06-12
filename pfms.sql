/*
 Navicat Premium Dump SQL

 Source Server         : localhost_3306
 Source Server Type    : MySQL
 Source Server Version : 80407 (8.4.7)
 Source Host           : localhost:3306
 Source Schema         : pfms

 Target Server Type    : MySQL
 Target Server Version : 80407 (8.4.7)
 File Encoding         : 65001

 Date: 17/01/2026 15:26:57
*/

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ----------------------------
-- Table structure for catalog_template_items
-- ----------------------------
DROP TABLE IF EXISTS `catalog_template_items`;
CREATE TABLE `catalog_template_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `template_id` bigint NOT NULL,
  `parent_id` bigint DEFAULT NULL,
  `serial` varchar(64) DEFAULT NULL,
  `name` varchar(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci DEFAULT NULL,
  `year` varchar(10) DEFAULT NULL,
  `month` varchar(10) DEFAULT NULL,
  `day` varchar(10) DEFAULT NULL,
  `pages` int DEFAULT NULL,
  `remark` text,
  `sort_order` int DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `template_id` (`template_id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `catalog_template_items_ibfk_1` FOREIGN KEY (`template_id`) REFERENCES `catalog_templates` (`id`),
  CONSTRAINT `catalog_template_items_ibfk_2` FOREIGN KEY (`parent_id`) REFERENCES `catalog_template_items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=61 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of catalog_template_items
-- ----------------------------
BEGIN;
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (1, 1, NULL, '一', '履历材料', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (2, 1, 1, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 21:13:23');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (3, 1, 1, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 21:13:22');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (4, 1, NULL, '二', '自传材料', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (5, 1, 4, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 21:13:23');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (6, 1, 4, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 21:13:24');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (7, 1, NULL, '三', '考察、鉴定、考核材料', NULL, NULL, NULL, NULL, NULL, 3, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (8, 1, 7, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 21:13:24');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (9, 1, 7, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 21:13:25');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (10, 1, NULL, '四', '学历学位、职称、学术、培训等材料', NULL, NULL, NULL, NULL, NULL, 4, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (11, 1, 10, '4-1', '学位学位材料', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (12, 1, 11, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (13, 1, 11, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (14, 1, 10, '4-2', '评聘专业技术职务材料', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (15, 1, 14, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (16, 1, 14, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (17, 1, 10, '4-3', '反映科研学术水平材料', NULL, NULL, NULL, NULL, NULL, 3, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (18, 1, 17, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (19, 1, 17, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (20, 1, 10, '4-4', '培训材料', NULL, NULL, NULL, NULL, NULL, 4, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (21, 1, 20, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (22, 1, 20, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (23, 1, NULL, '五', '政审、审计、审核材料', NULL, NULL, NULL, NULL, NULL, 5, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (24, 1, 23, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (25, 1, 23, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (26, 1, NULL, '六', '党团材料', NULL, NULL, NULL, NULL, NULL, 6, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (27, 1, 26, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (28, 1, 26, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (29, 1, NULL, '七', '奖励材料', NULL, NULL, NULL, NULL, NULL, 7, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (30, 1, 29, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (31, 1, 29, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (32, 1, NULL, '八', '处理处分材料', NULL, NULL, NULL, NULL, NULL, 8, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (33, 1, 32, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (34, 1, 32, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (35, 1, NULL, '九', '工资、任免、出国、会议等材料', NULL, NULL, NULL, NULL, NULL, 9, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (36, 1, 35, '9-1', '工资材料', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (37, 1, 36, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (38, 1, 36, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (39, 1, 35, '9-2', '任免材料', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (40, 1, 39, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (41, 1, 39, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (42, 1, 35, '9-3', '出国(境)材料', NULL, NULL, NULL, NULL, NULL, 3, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (43, 1, 42, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (44, 1, 42, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (45, 1, 35, '9-4', '会议代表材料', NULL, NULL, NULL, NULL, NULL, 4, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (46, 1, 45, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (47, 1, 45, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (48, 1, NULL, '十', '其他材料', NULL, NULL, NULL, NULL, NULL, 10, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (49, 1, 48, '', '', NULL, NULL, NULL, NULL, NULL, 1, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_template_items` (`id`, `template_id`, `parent_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `sort_order`, `created_at`, `updated_at`) VALUES (50, 1, 48, '', '', NULL, NULL, NULL, NULL, NULL, 2, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
COMMIT;

-- ----------------------------
-- Table structure for catalog_templates
-- ----------------------------
DROP TABLE IF EXISTS `catalog_templates`;
CREATE TABLE `catalog_templates` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `description` text,
  `owner_id` bigint NOT NULL,
  `visibility` enum('private','shared') NOT NULL,
  `is_default` int DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `owner_id` (`owner_id`),
  CONSTRAINT `catalog_templates_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of catalog_templates
-- ----------------------------
BEGIN;
INSERT INTO `catalog_templates` (`id`, `name`, `description`, `owner_id`, `visibility`, `is_default`, `created_at`, `updated_at`) VALUES (1, '干部档案目录', '干部档案目录模板', 1, 'shared', 0, '2026-01-13 16:42:38', '2026-01-13 16:42:38');
INSERT INTO `catalog_templates` (`id`, `name`, `description`, `owner_id`, `visibility`, `is_default`, `created_at`, `updated_at`) VALUES (2, '测试模板', NULL, 1, 'shared', NULL, '2026-01-13 17:45:28', '2026-01-13 17:45:28');
COMMIT;

-- ----------------------------
-- Table structure for entries
-- ----------------------------
DROP TABLE IF EXISTS `entries`;
CREATE TABLE `entries` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `owner_id` bigint NOT NULL,
  `template_id` bigint NOT NULL,
  `name` varchar(128) DEFAULT NULL,
  `emp_no` varchar(64) DEFAULT NULL,
  `role_title` varchar(128) DEFAULT NULL,
  `phone` varchar(64) DEFAULT NULL,
  `status` varchar(64) DEFAULT NULL,
  `org_path` varchar(255) DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  `org_unit_id` bigint DEFAULT NULL,
  `id_card` varchar(32) DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `owner_id` (`owner_id`),
  KEY `template_id` (`template_id`),
  KEY `idx_entries_org_unit_id` (`org_unit_id`),
  CONSTRAINT `entries_ibfk_1` FOREIGN KEY (`owner_id`) REFERENCES `users` (`id`),
  CONSTRAINT `entries_ibfk_2` FOREIGN KEY (`template_id`) REFERENCES `catalog_templates` (`id`),
  CONSTRAINT `fk_entries_org_unit` FOREIGN KEY (`org_unit_id`) REFERENCES `org_units` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of entries
-- ----------------------------
BEGIN;
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (1, 1, 1, '王小明', 'EMP-1001', '管理员', '13800000001', '在岗', '国家图书馆/总馆', '2026-01-13 21:21:40', '2026-01-16 16:44:13', 2, '123456324535');
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (2, 1, 1, '李主任', 'EMP-1002', '东馆负责人', '13800000002', '在岗', '国家图书馆/东馆', '2026-01-13 21:24:12', '2026-01-13 21:24:12', 3, '345345');
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (3, 1, 1, '周老师', 'EMP-1003', '少儿部', '13800000003', '休假', '国家图书馆/东馆/少儿部', '2026-01-13 21:24:12', '2026-01-13 21:24:12', 4, '54654456');
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (4, 1, 1, 'zeng', '123124', '123234', '12124', NULL, NULL, '2026-01-16 15:49:13', '2026-01-16 15:49:13', 6, '5105251999123123123');
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (5, 1, 1, 'zeng', '123', '214', '123', '123', NULL, '2026-01-16 16:46:04', '2026-01-16 16:46:04', 2, '12312312');
INSERT INTO `entries` (`id`, `owner_id`, `template_id`, `name`, `emp_no`, `role_title`, `phone`, `status`, `org_path`, `created_at`, `updated_at`, `org_unit_id`, `id_card`) VALUES (6, 1, 1, 'zeng', '324', '234', '234345', NULL, NULL, '2026-01-17 14:42:32', '2026-01-17 15:22:31', 10, '2343242');
COMMIT;

-- ----------------------------
-- Table structure for entry_catalog_items
-- ----------------------------
DROP TABLE IF EXISTS `entry_catalog_items`;
CREATE TABLE `entry_catalog_items` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `entry_id` bigint NOT NULL,
  `template_item_id` bigint NOT NULL,
  `serial` varchar(64) DEFAULT NULL,
  `name` varchar(255) DEFAULT NULL,
  `year` varchar(10) DEFAULT NULL,
  `month` varchar(10) DEFAULT NULL,
  `day` varchar(10) DEFAULT NULL,
  `pages` int DEFAULT NULL,
  `remark` text,
  `attachment_path` text,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `entry_id` (`entry_id`),
  KEY `template_item_id` (`template_item_id`),
  CONSTRAINT `entry_catalog_items_ibfk_1` FOREIGN KEY (`entry_id`) REFERENCES `entries` (`id`),
  CONSTRAINT `entry_catalog_items_ibfk_2` FOREIGN KEY (`template_item_id`) REFERENCES `catalog_template_items` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=68 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of entry_catalog_items
-- ----------------------------
BEGIN;
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (2, 1, 2, '1-1', '履历材料-1', '2026', '01', '01', 5, 'beizhu 01', NULL, '2026-01-13 21:26:58', '2026-01-14 11:31:30');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (4, 1, 4, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (5, 1, 5, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (6, 1, 6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (7, 1, 7, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (8, 1, 8, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (9, 1, 9, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (10, 1, 10, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (11, 1, 11, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (12, 1, 12, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (13, 1, 13, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (14, 1, 14, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (15, 1, 15, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (16, 1, 16, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (17, 1, 17, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (18, 1, 18, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (19, 1, 19, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (20, 1, 20, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (21, 1, 21, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (22, 1, 22, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (23, 1, 23, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (24, 1, 24, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (25, 1, 25, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (26, 1, 26, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (27, 1, 27, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (28, 1, 28, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (29, 1, 29, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (30, 1, 30, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (31, 1, 31, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (32, 1, 32, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (33, 1, 33, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (34, 1, 34, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (35, 1, 35, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (36, 1, 36, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (37, 1, 37, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (38, 1, 38, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (39, 1, 39, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (40, 1, 40, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (41, 1, 41, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (42, 1, 42, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (43, 1, 43, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (44, 1, 44, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (45, 1, 45, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (46, 1, 46, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (47, 1, 47, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (48, 1, 48, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (49, 1, 49, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (50, 1, 50, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:28:21', '2026-01-13 21:28:21');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (55, 1, 1, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '2026-01-13 21:57:55', '2026-01-13 21:58:53');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (56, 1, 3, '1-2', '履历材料-2', '2026', '01', '02', 5, '42324', NULL, '2026-01-14 11:13:10', '2026-01-14 11:31:33');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (64, 6, 2, '001', '履历材料-1', '2026', '01', '17', 5, NULL, NULL, '2026-01-17 14:43:49', '2026-01-17 14:59:26');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (65, 6, 3, '002', '履历材料-2', '2027', '01', '18', 5, NULL, NULL, '2026-01-17 14:43:52', '2026-01-17 14:59:28');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (66, 6, 5, '001', '自传材料-1', '2026', '01', '19', 5, NULL, NULL, '2026-01-17 14:45:04', '2026-01-17 14:59:29');
INSERT INTO `entry_catalog_items` (`id`, `entry_id`, `template_item_id`, `serial`, `name`, `year`, `month`, `day`, `pages`, `remark`, `attachment_path`, `created_at`, `updated_at`) VALUES (67, 6, 6, '002', '自传材料-2', '2026', '01', '20', 5, NULL, NULL, '2026-01-17 14:45:05', '2026-01-17 14:59:31');
COMMIT;

-- ----------------------------
-- Table structure for entry_item_images
-- ----------------------------
DROP TABLE IF EXISTS `entry_item_images`;
CREATE TABLE `entry_item_images` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `entry_catalog_item_id` bigint NOT NULL,
  `image_type` enum('original','retouched') NOT NULL,
  `file_path` text NOT NULL,
  `file_name` varchar(255) DEFAULT NULL,
  `file_size` bigint DEFAULT NULL,
  `mime_type` varchar(128) DEFAULT NULL,
  `checksum` varchar(128) DEFAULT NULL,
  `width` int DEFAULT NULL,
  `height` int DEFAULT NULL,
  `sort_order` int DEFAULT NULL,
  `original_id` bigint DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `entry_catalog_item_id` (`entry_catalog_item_id`),
  KEY `original_id` (`original_id`),
  CONSTRAINT `entry_item_images_ibfk_1` FOREIGN KEY (`entry_catalog_item_id`) REFERENCES `entry_catalog_items` (`id`),
  CONSTRAINT `entry_item_images_ibfk_2` FOREIGN KEY (`original_id`) REFERENCES `entry_item_images` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=24 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of entry_item_images
-- ----------------------------
BEGIN;
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (1, 2, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/2/DSC_8088.jpg', 'DSC_8088.jpg', 19536757, 'image/jpeg', NULL, NULL, NULL, 1, NULL, '2026-01-14 15:38:43', '2026-01-14 15:38:43');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (2, 56, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0001.tif', '0001.tif', 476470, 'image/tiff', NULL, NULL, NULL, 1, NULL, '2026-01-14 16:58:09', '2026-01-14 16:58:09');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (3, 56, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0002.tif', '0002.tif', 469753, 'image/tiff', NULL, NULL, NULL, 2, NULL, '2026-01-14 16:58:09', '2026-01-14 16:58:09');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (4, 56, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0003.tif', '0003.tif', 486286, 'image/tiff', NULL, NULL, NULL, 3, NULL, '2026-01-14 16:58:09', '2026-01-14 16:58:09');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (5, 56, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0004.tif', '0004.tif', 472105, 'image/tiff', NULL, NULL, NULL, 4, NULL, '2026-01-14 16:58:09', '2026-01-14 16:58:09');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (6, 56, 'original', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0005.tif', '0005.tif', 468497, 'image/tiff', NULL, NULL, NULL, 5, NULL, '2026-01-14 16:58:09', '2026-01-14 16:58:09');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (13, 56, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0001_retouched.tif', '0001_retouched.tif', 26530718, 'image/tiff', NULL, NULL, NULL, 1, 2, '2026-01-15 13:18:16', '2026-01-16 16:06:17');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (14, 56, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0002_retouched.tif', '0002_retouched.tif', 26523140, 'image/tiff', NULL, NULL, NULL, 2, 3, '2026-01-15 15:31:06', '2026-01-16 16:05:53');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (15, 56, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0005_retouched.tif', '0005_retouched.tif', 26517284, 'image/tiff', NULL, NULL, NULL, 5, 6, '2026-01-15 15:35:21', '2026-01-16 16:08:40');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (16, 56, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0003_retouched.tif', '0003_retouched.tif', 26505065, 'image/tiff', NULL, NULL, NULL, 3, 4, '2026-01-16 16:06:01', '2026-01-16 16:06:01');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (17, 56, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/1/3/0004_retouched.tif', '0004_retouched.tif', 26515562, 'image/tiff', NULL, NULL, NULL, 4, 5, '2026-01-16 16:08:15', '2026-01-16 16:09:15');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (18, 64, 'original', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0001.tif', '0001.tif', 476470, 'image/tiff', NULL, NULL, NULL, 1, NULL, '2026-01-17 14:48:41', '2026-01-17 14:48:41');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (19, 64, 'original', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0002.tif', '0002.tif', 469753, 'image/tiff', NULL, NULL, NULL, 2, NULL, '2026-01-17 14:48:41', '2026-01-17 14:48:41');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (20, 64, 'original', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0003.tif', '0003.tif', 486286, 'image/tiff', NULL, NULL, NULL, 3, NULL, '2026-01-17 14:48:41', '2026-01-17 14:48:41');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (21, 64, 'original', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0004.tif', '0004.tif', 472105, 'image/tiff', NULL, NULL, NULL, 4, NULL, '2026-01-17 14:48:41', '2026-01-17 14:48:41');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (22, 64, 'original', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0005.tif', '0005.tif', 468497, 'image/tiff', NULL, NULL, NULL, 5, NULL, '2026-01-17 14:48:41', '2026-01-17 14:48:41');
INSERT INTO `entry_item_images` (`id`, `entry_catalog_item_id`, `image_type`, `file_path`, `file_name`, `file_size`, `mime_type`, `checksum`, `width`, `height`, `sort_order`, `original_id`, `created_at`, `updated_at`) VALUES (23, 64, 'retouched', '/home/happy/company/Personnel File Management System qt/data/images/6/2/0001_retouched.tif', '0001_retouched.tif', 26530718, 'image/tiff', NULL, NULL, NULL, 1, 18, '2026-01-17 14:49:19', '2026-01-17 14:58:42');
COMMIT;

-- ----------------------------
-- Table structure for org_units
-- ----------------------------
DROP TABLE IF EXISTS `org_units`;
CREATE TABLE `org_units` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `parent_id` bigint DEFAULT NULL,
  `name` varchar(255) NOT NULL,
  `code` varchar(64) DEFAULT NULL,
  `contact` varchar(128) DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  KEY `parent_id` (`parent_id`),
  CONSTRAINT `org_units_ibfk_1` FOREIGN KEY (`parent_id`) REFERENCES `org_units` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of org_units
-- ----------------------------
BEGIN;
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (1, NULL, '国家图书馆', 'TEST-0001', '', '2026-01-16 15:22:13', '2026-01-16 15:22:13');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (2, 1, '总馆', 'TEST-0001-01', '', '2026-01-16 15:22:41', '2026-01-16 15:22:41');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (3, 1, '东馆', 'TEST-0001-02', '', '2026-01-16 15:23:04', '2026-01-16 15:23:04');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (4, 3, '少儿部', 'TEST-0001-02-01', '', '2026-01-16 15:23:23', '2026-01-16 15:23:23');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (5, NULL, 'CUIT', 'CUIT-0001', '', '2026-01-16 15:27:16', '2026-01-16 15:27:16');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (6, 5, 'cs-0001-01', '', '', '2026-01-16 15:27:40', '2026-01-16 15:27:40');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (7, NULL, 'TEST', 'TEST01-01', '', '2026-01-17 14:23:42', '2026-01-17 14:23:42');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (8, 7, 'TEST-01', 'TEST01-01-01', '', '2026-01-17 14:24:03', '2026-01-17 14:24:03');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (9, 7, 'TEST-02', 'TEST01-01-02', '', '2026-01-17 14:24:29', '2026-01-17 14:24:29');
INSERT INTO `org_units` (`id`, `parent_id`, `name`, `code`, `contact`, `created_at`, `updated_at`) VALUES (10, 8, 'TEST-01-01', '123465', '', '2026-01-17 14:24:49', '2026-01-17 14:24:49');
COMMIT;

-- ----------------------------
-- Table structure for users
-- ----------------------------
DROP TABLE IF EXISTS `users`;
CREATE TABLE `users` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `username` varchar(64) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `display_name` varchar(128) DEFAULT NULL,
  `theme` varchar(10) DEFAULT NULL,
  `remember_pwd` int DEFAULT NULL,
  `created_at` datetime DEFAULT (now()),
  `updated_at` datetime DEFAULT (now()),
  PRIMARY KEY (`id`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------
-- Records of users
-- ----------------------------
BEGIN;
INSERT INTO `users` (`id`, `username`, `password_hash`, `display_name`, `theme`, `remember_pwd`, `created_at`, `updated_at`) VALUES (1, 'admin', '123456', '管理员', 'light', 0, '2026-01-13 16:29:45', '2026-01-13 16:29:45');
COMMIT;

SET FOREIGN_KEY_CHECKS = 1;
