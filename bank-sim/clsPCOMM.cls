VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "clsPCOMM"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

' ==============================================================================
' CLASE: clsPCOMM
' Simula la interfaz de IBM Personal Communications (PCOMM)
' Permite alternar entre una sesion real y una simulacion visual en Excel.
' ==============================================================================

Private pIsSimulated As Boolean
Private pPS As Object ' autECLPS
Private pOIA As Object ' autECLOIA
Private pSheet As Worksheet

' Inicializa la conexion
' sessionName: Letra de la sesion (A, B, etc.)
' simulated: Si es True, usa la hoja SIM_TERMINAL en lugar de PCOMM real
Public Sub Conn(Optional sessionName As String = "A", Optional simulated As Boolean = True)
    pIsSimulated = simulated
    If pIsSimulated Then
        ' Obtener la hoja de terminal via el modulo ModTerminal
        On Error Resume Next
        Set pSheet = ThisWorkbook.Worksheets("SIM_TERMINAL")
        If pSheet Is Nothing Then
            Set pSheet = ThisWorkbook.Worksheets.Add
            pSheet.Name = "SIM_TERMINAL"
        End If
        On Error GoTo 0
    Else
        ' Conexion real a IBM PCOMM
        Set pPS = CreateObject("PCOMM.autECLPS")
        Set pOIA = CreateObject("PCOMM.autECLOIA")
        pPS.SetConnectionByName sessionName
        pOIA.SetConnectionByName sessionName
    End If
End Sub

' Escribe texto en una posicion especifica (Fila, Columna)
Public Sub SetText(text As String, row As Integer, col As Integer)
    If pIsSimulated Then
        Dim i As Integer
        For i = 1 To Len(text)
            If col + i - 1 <= 80 Then
                pSheet.Cells(row, col + i - 1).Value = Mid(text, i, 1)
            End If
        Next i
    Else
        pPS.SetText text, row, col
    End If
End Sub

' Lee texto de la pantalla
Public Function GetText(row As Integer, col As Integer, length As Integer) As String
    If pIsSimulated Then
        Dim i As Integer, res As String
        res = ""
        For i = 0 To length - 1
            res = res & pSheet.Cells(row, col + i).Value
        Next i
        GetText = res
    Else
        GetText = pPS.GetText(row, col, length)
    End If
End Function

' Envia una tecla de control (ej: [enter], [pf3])
Public Sub SendKeys(keys As String)
    If pIsSimulated Then
        ' En simulacion, delegamos la respuesta a ModScreens
        If keys = "[enter]" Then
            ' Llamada dinamica al procesador de pantallas
            Application.Run "ModScreens.ProcesarComando", Me
        End If
        DoEvents
    Else
        pPS.SendKeys keys
    End If
End Sub

' Espera a que la terminal este lista para recibir input
Public Sub WaitReady(Optional ms As Long = 3000)
    If Not pIsSimulated Then
        pOIA.WaitForInputReady ms
    Else
        ' En simulacion solo damos un respiro al procesador
        DoEvents
    End If
End Sub

' Propiedad para saber si estamos en modo simulado
Public Property Get IsSimulated() As Boolean
    IsSimulated = pIsSimulated
End Property
