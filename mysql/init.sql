-- BioHazard CTF Lab - MySQL 初始化脚本
CREATE DATABASE IF NOT EXISTS corp CHARACTER SET utf8mb4;
USE corp;

CREATE TABLE IF NOT EXISTS users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  username VARCHAR(64),
  password VARCHAR(64),
  role VARCHAR(16)
);

CREATE TABLE IF NOT EXISTS flags (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(64),
  value VARCHAR(128)
);

INSERT INTO users(username,password,role) VALUES
  ('admin','admin@123','admin'),
  ('guest','guest123','user');

INSERT INTO flags(name,value) VALUES
  ('flag2_db','flag{C0ngr4ts_Y0u_R34d_DB}');

-- 业务应用账号 (Web 容器用它连库)
CREATE USER IF NOT EXISTS 'corp_app'@'%' IDENTIFIED BY 'CorpApp@2026';
GRANT SELECT, INSERT, UPDATE, DELETE ON corp.* TO 'corp_app'@'%';
FLUSH PRIVILEGES;