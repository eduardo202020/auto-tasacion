Option Explicit

' ==============================================================================
' MODULO: ModRobot
' Orquestador de la automatizacion de validacion bancaria.
' ==============================================================================

Sub IniciarProcesamientoAutomatico()
    Dim app As New clsPCOMM
    Dim ws As Worksheet, wsRep As Worksheet
    Dim fila As Long, ultimaFila As Long, filaRep As Long
    Dim nroPrestamo As String, titularEsperado As String, titularExtraido As String
    Dim estado As String
    
    Set ws = ThisWorkbook.Worksheets("Tasaciones")
    ultimaFila = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    
    ' 1. Configurar Hoja de Reporte
    On Error Resume Next
    Set wsRep = ThisWorkbook.Worksheets("REPORTE_FINAL")
    If wsRep Is Nothing Then Set wsRep = ThisWorkbook.Worksheets.Add(After:=ws): wsRep.Name = "REPORTE_FINAL"
    On Error GoTo 0
    wsRep.Cells.Clear
    wsRep.Range("A1:E1").Value = Array("PRESTAMO", "ESPERADO", "BANCO", "RESULTADO", "HORA")
    wsRep.Range("A1:E1").Font.Bold = True
    filaRep = 2
    
    ' 2. Iniciar Terminal Virtual
    ModTerminal.PrepararPantalla
    app.Conn simulated:=True
    ThisWorkbook.Worksheets("SIM_TERMINAL").Activate
    
    ' 3. Navegacion Inicial: Menu -> QSP (Latencia 5s)
    ModScreens.MostrarMenuPrincipal app
    app.SetText "QSP", 24, 14
    DoEvents: Application.Wait (Now + TimeValue("0:00:05"))
    app.SendKeys "[enter]"
    
    ' 4. Bucle de Procesamiento por Fila
    For fila = 2 To ultimaFila
        nroPrestamo = Trim(ws.Cells(fila, 26).Value) ' Columna Z
        titularEsperado = UCase(Trim(ws.Cells(fila, 27).Value)) ' Columna AA
        
        If nroPrestamo <> "" Then
            ' Limpiar y escribir en pantalla de busqueda
            ModScreens.MostrarQSP app
            app.SetText nroPrestamo, 5, 22
            DoEvents: Application.Wait (Now + TimeValue("0:00:05")) ' Latencia ingreso
            
            ' Ejecutar y esperar respuesta
            app.SendKeys "[enter]"
            DoEvents: Application.Wait (Now + TimeValue("0:00:05")) ' Latencia red bancaria
            
            ' Extraer resultado (Fila 11, Col 14)
            titularExtraido = Trim(app.GetText(11, 14, 40))
            
            ' Validar coincidencia
            If titularExtraido = "" Or InStr(1, titularExtraido, "ERROR", vbTextCompare) > 0 Then
                estado = "NO ENCONTRADO"
            ElseIf InStr(1, titularExtraido, titularEsperado, vbTextCompare) > 0 Or InStr(1, titularEsperado, titularExtraido, vbTextCompare) > 0 Then
                estado = "VALIDADO OK"
            Else
                estado = "DISCREPANCIA"
            End If
            
            ' Llenar Fila de Reporte
            wsRep.Cells(filaRep, 1).Value = nroPrestamo
            wsRep.Cells(filaRep, 2).Value = titularEsperado
            wsRep.Cells(filaRep, 3).Value = titularExtraido
            wsRep.Cells(filaRep, 4).Value = estado
            wsRep.Cells(filaRep, 5).Value = Format(Now, "hh:mm:ss")
            
            ' Formato condicional
            If estado = "VALIDADO OK" Then
                wsRep.Cells(filaRep, 4).Interior.Color = RGB(200, 230, 201)
            Else
                wsRep.Cells(filaRep, 4).Interior.Color = RGB(255, 205, 210)
            End If
            
            filaRep = filaRep + 1
            DoEvents
        End If
    Next fila
    
    ' 5. Finalizar
    wsRep.Columns("A:E").AutoFit
    wsRep.Activate
    MsgBox "Automatizacion completada con exito.", vbInformation
End Sub
