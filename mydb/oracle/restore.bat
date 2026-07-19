@echo off
sqlplus system/manager1 as sysdba @create_user.sql
imp msudle/msudles ignore=y parfile=restore.dat
pause