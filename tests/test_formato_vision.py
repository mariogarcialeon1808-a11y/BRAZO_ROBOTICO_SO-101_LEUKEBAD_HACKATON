import pytest
from so101er.aplicacion_servicios import validar_bloques


@pytest.mark.parametrize('region',[
    [100,200,700,900],[[100,200],[700,900]],[[700,900],[100,200]],
    {'ymin':100,'xmin':200,'ymax':700,'xmax':900},
    {'y_min':100,'x_min':200,'y_max':700,'x_max':900},
])
def test_formatos_equivalentes_de_region_preservan_coordenadas(region):
    b={'texto':'Mira esta región del paisaje.','tipo':'region','brazo':'izq','region':region,'ancla':2}
    assert validar_bloques({'bloques':[b]})[0]['region']==[[100,200],[700,900]]


@pytest.mark.parametrize('region',[None,'el cielo',[1,2,3],[0,0,1001,900],[[0,0],[0,800]],[[0,0],[float('nan'),1]]])
def test_no_inventa_regiones_ni_admite_datos_invalidos(region):
    b={'texto':'Mira esta región del paisaje.','tipo':'region','brazo':'izq','region':region,'ancla':2}
    with pytest.raises((ValueError,TypeError)):validar_bloques({'bloques':[b]})
