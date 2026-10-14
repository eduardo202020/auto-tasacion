Attribute VB_Name = "AutoTasacion3270"
Option Explicit

' Módulo de ejecución por lote para la plantilla MASIVO.
' Requiere que la clase CONEXION de la plantilla esté disponible y que PCOMM
' tenga la sesión indicada ya autenticada en la pantalla de espera.

Public Sub EjecutarLote3270(ByVal primeraFila As Long, ByVal ultimaFila As Long, _
                            ByVal carpetaEvidencia As String, ByVal nombreSesion As String)
    Dim ws As Worksheet
    Dim con As Object
    Dim fila As Long
    Dim centroActual As String

    Set ws = ThisWorkbook.Worksheets("MASIVO")
    ValidarRangoPad ws, primeraFila, ultimaFila
    CrearCarpetasPad carpetaEvidencia

    Set con = New CONEXION
    con.init nombreSesion

    IrAI003Pad con
    centroActual = Trim$(con.Leer(2, 2, 4))
    If centroActual <> "0727" Then
        CambiarCentroPad con, "0727"
        IrAI003Pad con
    End If

    For fila = primeraFila To ultimaFila
        ProcesarFila3270Pad con, ws, fila, carpetaEvidencia
    Next fila

    ThisWorkbook.Save
End Sub

Private Sub ValidarRangoPad(ByVal ws As Worksheet, ByVal primeraFila As Long, ByVal ultimaFila As Long)
    Dim ultimaConDato As Long

    ultimaConDato = ws.Cells(ws.Rows.Count, "A").End(xlUp).Row
    If primeraFila < 2 Or ultimaFila < primeraFila Or ultimaFila > ultimaConDato Then
        Err.Raise vbObjectError + 3270, "EjecutarLote3270", "Rango de filas inválido para MASIVO."
    End If
End Sub

Private Sub ProcesarFila3270Pad(ByVal con As Object, ByVal ws As Worksheet, _
                                ByVal fila As Long, ByVal carpetaEvidencia As String)
    Dim prestamo As String
    Dim importe As String
    Dim valorBien As String
    Dim direccion As String
    Dim direccion1 As String
    Dim ubicacion As String
    Dim ubicacion1 As String
    Dim referencia As String
    Dim municipio As String
    Dim codigoDistrito As String
    Dim codigoProvincia As String
    Dim codigoDepartamento As String
    Dim numeroExterior As String
    Dim numeroInterior As String
    Dim claseInmueble As String
    Dim pisos As String
    Dim sotanos As String
    Dim anioConstruccion As String
    Dim tipoInmueble As String
    Dim mensajePantalla As String
    Dim altaSeguro As String

    On Error GoTo ErrorFila

    prestamo = Trim$(CStr(ws.Cells(fila, "A").Value))
    If Len(prestamo) <> 20 Or Not EsNumericoPad(prestamo) Then
        RegistrarResultadoPad ws, fila, "BLOQUEADO", "PRESTAMO_INVALIDO"
        Exit Sub
    End If

    importe = Trim$(CStr(ws.Cells(fila, "E").Value))
    valorBien = Trim$(CStr(ws.Cells(fila, "C").Value))
    direccion = Trim$(CStr(ws.Cells(fila, "G").Value))
    direccion1 = Trim$(CStr(ws.Cells(fila, "H").Value))
    ubicacion = Trim$(CStr(ws.Cells(fila, "M").Value))
    ubicacion1 = Trim$(CStr(ws.Cells(fila, "N").Value))
    referencia = Trim$(CStr(ws.Cells(fila, "K").Value))
    municipio = Trim$(CStr(ws.Cells(fila, "O").Value))
    codigoDistrito = Trim$(CStr(ws.Cells(fila, "P").Value))
    codigoProvincia = Trim$(CStr(ws.Cells(fila, "R").Value))
    codigoDepartamento = Trim$(CStr(ws.Cells(fila, "T").Value))
    numeroExterior = Trim$(CStr(ws.Cells(fila, "I").Value))
    numeroInterior = Trim$(CStr(ws.Cells(fila, "J").Value))
    claseInmueble = Trim$(CStr(ws.Cells(fila, "U").Value))
    pisos = Trim$(CStr(ws.Cells(fila, "V").Value))
    sotanos = Trim$(CStr(ws.Cells(fila, "W").Value))
    anioConstruccion = Trim$(CStr(ws.Cells(fila, "X").Value))
    tipoInmueble = UCase$(Trim$(CStr(ws.Cells(fila, "B").Value)))

    IrAI003Pad con
    con.Escribir "01", 5, 14
    con.Escribir prestamo, 6, 18
    con.IngresarTecla "enter"
    con.ColocarCursor 7, 14
    con.IngresarTecla "fin"
    con.Escribir importe, 7, 14
    con.Escribir valorBien, 9, 56
    con.IngresarTecla "f4"
    con.Escribir "c", 12, 20

    If tipoInmueble = "DEPARTAMENTO" Then
        con.Escribir "D", 12, 41
    Else
        con.Escribir "C", 12, 41
    End If

    con.Escribir "B", 12, 67
    con.IngresarTecla "f4"
    mensajePantalla = Trim$(con.Leer(3, 2, 80))
    If InStr(1, mensajePantalla, "ICA0015", vbTextCompare) > 0 Then
        RegistrarResultadoPad ws, fila, "MENSAJE_3270", mensajePantalla
        con.IngresarTecla "pausa"
        Exit Sub
    End If

    con.Escribir direccion, 13, 15
    con.Escribir direccion1, 13, 21
    con.Escribir numeroExterior, 14, 11
    con.Escribir numeroInterior, 14, 29
    con.Escribir referencia, 14, 49
    con.Escribir ubicacion, 15, 11
    con.Escribir ubicacion1, 15, 17
    con.Escribir municipio, 16, 15
    con.Escribir codigoDistrito, 17, 18
    con.Escribir codigoProvincia, 17, 38
    con.Escribir codigoDepartamento, 17, 56
    con.Escribir "PER", 17, 67

    con.Escribir Format$(Val(pisos), "00"), 22, 15
    If Val(sotanos) = 0 Then
        con.Escribir "", 22, 33
    Else
        con.Escribir Format$(Val(sotanos), "00"), 22, 33
    End If
    con.Escribir claseInmueble, 22, 51
    con.Escribir "001", 22, 61
    con.Escribir anioConstruccion, 22, 73
    con.ColocarCursor 7, 14
    con.IngresarTecla "fin"
    con.Escribir importe, 7, 14
    con.IngresarTecla "f8"

    altaSeguro = Trim$(con.Leer(3, 20, 20))
    GuardarPantallaPad con, carpetaEvidencia, prestamo
    con.IngresarTecla "pausa"

    If Len(altaSeguro) > 0 Then
        RegistrarResultadoPad ws, fila, "COMPLETADO", altaSeguro
    Else
        RegistrarResultadoPad ws, fila, "SIN_RESPUESTA", "SIN_VALOR_EN_PANTALLA"
    End If
    Exit Sub

ErrorFila:
    RegistrarResultadoPad ws, fila, "ERROR_TECNICO", Left$(Err.Description, 200)
    On Error Resume Next
    con.IngresarTecla "pausa"
    On Error GoTo 0
End Sub

Private Sub IrAI003Pad(ByVal con As Object)
    con.IngresarTecla "pausa"
    con.Escribir "i003", 1, 1
    con.IngresarTecla "enter"
End Sub

Private Sub CambiarCentroPad(ByVal con As Object, ByVal centro As String)
    con.IngresarTecla "pausa"
    con.Escribir "qgtr", 1, 1
    con.IngresarTecla "enter"
    con.Escribir centro, 4, 34
    con.IngresarTecla "enter"
    con.IngresarTecla "pausa"
End Sub

Private Sub GuardarPantallaPad(ByVal con As Object, ByVal carpetaEvidencia As String, ByVal prestamo As String)
    Dim ws As Worksheet
    Dim indice As Long
    Dim textoLinea As String
    Dim destino As Range

    On Error GoTo Salir
    Set ws = ThisWorkbook.Worksheets("PRINT_PANTALLAS")
    ws.Range("A4:J27").UnMerge
    ws.Range("A4:J27").ClearContents

    For indice = 1 To 24
        textoLinea = Trim$(con.Leer(indice, 1, 80))
        Set destino = ws.Range("A" & (3 + indice) & ":J" & (3 + indice))
        If Len(textoLinea) > 0 Then
            destino.Merge
            destino.Value = textoLinea
            destino.HorizontalAlignment = xlLeft
            destino.VerticalAlignment = xlCenter
            destino.Font.Name = "Consolas"
            destino.Font.Size = 10
        End If
    Next indice

    ws.Range("A4:J27").ExportAsFixedFormat _
        Type:=xlTypePDF, _
        Filename:=carpetaEvidencia & "\3270_" & prestamo & ".pdf"
Salir:
    On Error Resume Next
    ws.Range("A4:J27").UnMerge
    On Error GoTo 0
End Sub

Private Sub RegistrarResultadoPad(ByVal ws As Worksheet, ByVal fila As Long, _
                                  ByVal estado As String, ByVal detalle As String)
    Dim traza As Worksheet
    Dim filaTraza As Long

    ws.Cells(fila, "Y").Value = detalle
    Set traza = ThisWorkbook.Worksheets("TRAZA_PAD")
    filaTraza = BuscarFilaTrazaPad(traza, fila)
    If filaTraza = 0 Then Exit Sub
    traza.Cells(filaTraza, "F").Value = estado
    traza.Cells(filaTraza, "G").Value = detalle
    traza.Cells(filaTraza, "I").Value = Now
End Sub

Private Function BuscarFilaTrazaPad(ByVal traza As Worksheet, ByVal filaMasivo As Long) As Long
    Dim ultimaFila As Long
    Dim fila As Long

    ultimaFila = traza.Cells(traza.Rows.Count, "A").End(xlUp).Row
    For fila = 2 To ultimaFila
        If CLng(Val(traza.Cells(fila, "A").Value)) = filaMasivo Then
            BuscarFilaTrazaPad = fila
            Exit Function
        End If
    Next fila
End Function

Private Function EsNumericoPad(ByVal valor As String) As Boolean
    Dim posicion As Long
    For posicion = 1 To Len(valor)
        If Mid$(valor, posicion, 1) < "0" Or Mid$(valor, posicion, 1) > "9" Then Exit Function
    Next posicion
    EsNumericoPad = True
End Function

Private Sub CrearCarpetasPad(ByVal ruta As String)
    Dim partes() As String
    Dim indice As Long
    Dim actual As String

    partes = Split(ruta, "\")
    If UBound(partes) = 0 Then Exit Sub
    actual = partes(0)
    For indice = 1 To UBound(partes)
        actual = actual & "\" & partes(indice)
        If Len(Dir$(actual, vbDirectory)) = 0 Then MkDir actual
    Next indice
End Sub
