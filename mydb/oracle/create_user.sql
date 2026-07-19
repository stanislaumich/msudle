spool create_user.log
shutdown immediate;
startup restrict;
ALTER DATABASE CHARACTER SET INTERNAL_USE CL8MSWIN1251;
shutdown immediate;
startup;
drop user msudle cascade;
create user msudle identified by msudle default tablespace users temporary tablespace temp;
grant dba to msudle;
grant create session to msudle;
spool off
exit;