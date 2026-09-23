Option Explicit

Public Sub ProcesarComando(ByRef term As Object)
    Dim pantallaActual As String
    pantallaActual = term.GetText(1, 1, 80)
    
    If InStr(1, pantallaActual, "MENU PRINCIPAL", vbTextCompare) > 0 Then
        Dim cmd As String
        cmd = UCase(Trim(term.GetText(24, 14, 10)))
        cmd = Replace(cmd, "_", "")
        If cmd = "QSP" Then MostrarQSP term
        
    ElseIf InStr(1, pantallaActual, "CONSULTA DE RELACIONES", vbTextCompare) > 0 Then
        Dim loan As String
        loan = Trim(term.GetText(5, 22, 20))
        loan = Replace(loan, "_", "")
        
        If loan <> "" And IsNumeric(loan) Then
            MostrarDetallePrestamo term, loan
        End If
    End If
End Sub

Public Sub MostrarMenuPrincipal(ByRef term As Object)
    ModTerminal.LimpiarPantalla
    term.SetText "--- SISTEMA CENTRAL BANCARIO - MENU PRINCIPAL ---", 1, 15
    term.SetText "TRANSACCIONES DISPONIBLES:", 4, 5
    term.SetText "QSP - CONSULTA DE RELACIONES BANCARIAS", 6, 5
    term.SetText "COMANDO ==>", 24, 2: term.SetText "____", 24, 14
End Sub

Public Sub MostrarQSP(ByRef term As Object)
    ModTerminal.LimpiarPantalla
    term.SetText "--- CONSULTA DE RELACIONES BANCARIAS (QSP) ---", 1, 18
    term.SetText "NUMERO DE PRESTAMO: _________________", 5, 2
    term.SetText "F3=ATRAS", 24, 2
End Sub

Public Sub MostrarDetallePrestamo(ByRef term As Object, loan As String)
    Dim ws As Worksheet, found As Range
    Set ws = ThisWorkbook.Worksheets("SIM_BANCO")
    Set found = ws.Columns(1).Find(What:=loan, LookIn:=xlValues, LookAt:=xlWhole)
    
    ModTerminal.LimpiarPantalla
    term.SetText "--- DATOS DEL CLIENTE ENCONTRADO (QSP) ---", 1, 18
    If Not found Is Nothing Then
        term.SetText "TITULAR: " & UCase(found.Offset(0, 3).Value), 11, 5
        term.SetText "DNI:     " & found.Offset(0, 1).Value, 12, 5
        term.SetText "ESTADO:  " & found.Offset(0, 4).Value, 13, 5
    Else
        term.SetText "ERROR: PRESTAMO NO ENCONTRADO", 11, 14
    End If
End Sub
