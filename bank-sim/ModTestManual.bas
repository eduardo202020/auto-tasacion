Attribute VB_Name = "ModTestManual"
Option Explicit

' ==============================================================================
' MODULO: ModTestManual (Corresponde a Módulo1 en el Excel)
' Macros para pruebas manuales y arranque rapido del simulador.
' ==============================================================================

Sub IniciarBancoSimulado()
    Dim app As New clsPCOMM
    
    ' 1. Preparamos la hoja visual
    ModTerminal.PrepararPantalla
    
    ' 2. Conectamos (en modo simulado)
    app.Conn simulated:=True
    
    ' 3. Mostramos el menú inicial
    ModScreens.MostrarMenuPrincipal app
    
    MsgBox "El simulador esta listo. Escribe 'QSP' en la linea inferior (donde estan las rayas) y presiona Enter.", vbInformation
End Sub
