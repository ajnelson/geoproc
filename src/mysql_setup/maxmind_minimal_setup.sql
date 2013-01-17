CREATE USER db_writer IDENTIFIED BY 'please_change_this_default_password';
CREATE USER db_reader IDENTIFIED BY 'please_change_this_default_password';
CREATE SCHEMA `maxmind`;
GRANT ALL PRIVILEGES ON `maxmind`.* TO `db_writer`@`%`;
GRANT SELECT ON `maxmind`.* TO `db_reader`@`%`;
