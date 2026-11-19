"""Qué hace la cara mientras los brazos gesticulan: hacia dónde mira y con qué ánimo.

Es una tabla, no una decisión del control: la cara solo recibe lo que los brazos ya van a hacer.
Los identificadores son los de la biblioteca de movimientos (docs/REGISTRO_EXPRESIVO.md).
"""
ARRIBA = {'D08', 'E08', 'E12', 'E15', 'E16', 'M21', 'M26', 'B10'}
ABAJO = {'D09', 'D10', 'E09', 'E17', 'M07', 'M18', 'M30', 'B11', 'B13'}
ANIMO = {
    'alegre': {'M20', 'M24', 'M02', 'M05', 'M15', 'M26', 'B09', 'B10', 'B11'},
    'serio': {'M03', 'M04', 'M16', 'M30', 'B14'},          # solo normas, negativas y prohibiciones
    'atento': {'M21', 'M28', 'D07', 'D11', 'D12', 'E17'},
    'duda': {'M22', 'M25', 'M27', 'M29', 'B12'},
    'pensativo': {'M11', 'M12', 'M31', 'B06', 'B17'},
}
DOS_BRAZOS = ('paisaje', 'cielo')


def de_bloque(bloque: dict, espejo: bool = False) -> dict:
    """{lado, vertical, animo} para el gesto de un bloque de la IA.

    lado: -1 mira a la izquierda de la pantalla, 1 a la derecha, 0 al frente. Mira hacia el brazo que hace
    el gesto principal; con los dos brazos, al frente. `espejo` lo invierte: es para cuando el público ve
    la cara de frente y los brazos le quedan cruzados.
    """
    movimientos = [m for m in (bloque.get('movimiento'), bloque.get('otro')) if m]
    tipo = bloque.get('tipo')
    lado = 0
    if tipo not in DOS_BRAZOS and not (movimientos and movimientos[0].startswith('B')):
        lado = 1 if bloque.get('brazo') == 'der' else -1
        if espejo:
            lado = -lado
    vertical = next((1 if m in ARRIBA else -1 for m in movimientos if m in ARRIBA or m in ABAJO), 0)
    if tipo == 'cielo':
        vertical = 1
    animo = next((nombre for m in movimientos for nombre, ids in ANIMO.items() if m in ids), 'neutro')
    if tipo in ('senalar', 'region') and animo == 'neutro':
        animo = 'atento'                  # al señalar algo de la imagen, la cara atiende a ello
    return {'lado': lado, 'vertical': vertical, 'animo': animo}
