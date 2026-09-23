Attribute VB_Name = "ModTerminal"
Option Explicit

' ==============================================================================
' MODULO: ModTerminal
' Se encarga de la parte visual de la Terminal Virtual 80x24 en Excel.
' ==============================================================================

Public Sub PrepararPantalla()
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Worksheets("SIM_TERMINAL")
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
        ws.Name = "SIM_TERMINAL"
    End If
    
    With ws
        .Cells.Clear
        .Cells.Interior.Color = RGB(0, 0, 0) ' Fondo Negro
        .Cells.Font.Name = "Consolas"
        .Cells.Font.Size = 10
        .Cells.Font.Color = RGB(0, 255, 0) ' Letras Verdes (Classic Terminal)
        
        ' Formatear cuadricula 80x24
        .Columns("A:CB").ColumnWidth = 1.6
        .Rows("1:24").RowHeight = 12.75
        .Columns("A:CB").HorizontalAlignment = xlCenter
        .Columns("A:CB").VerticalAlignment = xlCenter
    End With
    
    ActiveWindow.DisplayGridlines = False
    ActiveWindow.DisplayHeadings = False
    ws.Activate
End Sub

' Metodo para limpiar solo el contenido manteniendo el formato negro
Public Sub LimpiarPantalla()
    On Error Resume Next
    ThisWorkbook.Worksheets("SIM_TERMINAL").Cells.ClearContents
End Sub
