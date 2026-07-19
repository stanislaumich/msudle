rem @echo off
ren backup.dmp backup_prev.dmp
del backup.dmp
sqlplus msudle/msudle @backup.sql
exp msudle/msudle parfile=backup.dat
del *.log
rar a -m5 -ag_dd.mm.yyyy-hh-mi-ss backup @backup.lst
rem pause
