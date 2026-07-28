$PBExportHeader$genapp.sra
$PBExportComments$Edited via pb-orca-mcp end-to-end test
forward
global type genapp from application
end type
global transaction sqlca
global dynamicdescriptionarea sqlda
global dynamicstagingarea sqlsa
global error error
global message message
end forward

global type genapp from application
string appname = "genapp"
string appruntimeversion = "22.2.0.3397"
end type
global genapp genapp

on genapp.create
appname = "genapp"
message = create message
sqlca = create transaction
sqlda = create dynamicdescriptionarea
sqlsa = create dynamicstagingarea
error = create error
end on

on genapp.destroy
destroy( sqlca )
destroy( sqlda )
destroy( sqlsa )
destroy( error )
destroy( message )
end on

event open;//*-----------------------------------------------------------------*/
//*    open:  Application Open Script
//*           1) Opens Main window
//*    Modified by pb-orca-mcp on 2026-05-13
//*-----------------------------------------------------------------*/
Open ( w_genapp_main )
end event

