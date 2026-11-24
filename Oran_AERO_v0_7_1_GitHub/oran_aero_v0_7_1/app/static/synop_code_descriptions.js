/* Catálogo de descripciones para los formularios.
 * Descripciones fieles al sentido de las tablas de clave del SMN (noviembre 2022).
 * Centralizadas para no duplicar la terminología en cada formulario.
 */
window.OranSynopCodes = Object.freeze({
  cloud: {
    cl: { // 0513: nubes bajas
      '0': 'Sin nubes bajas (CL).',
      '1': 'Cúmulus humilis o fractocúmulus que no sean de mal tiempo, o ambos.',
      '2': 'Cúmulus mediocris o congestus, acompañados o no de otros cúmulus o estratocúmulus, con las bases a un mismo nivel.',
      '3': 'Cumulonimbus calvus; pueden coexistir cúmulus, estratocúmulus o estratos.',
      '4': 'Estratocúmulus cumulogenitus: procedentes de la extensión de cúmulus.',
      '5': 'Estratocúmulus que no sean cumulogenitus.',
      '6': 'Stratus nebulosus o fractostratus que no sean de mal tiempo, o ambos.',
      '7': 'Fractostratus o fractocúmulus de mal tiempo (pannus), generalmente debajo de altostratus o nimbostratus.',
      '8': 'Cúmulus y estratocúmulus no cumulogenitus, con sus bases a diferentes niveles.',
      '9': 'Cumulonimbus capillatus, frecuentemente con yunque; acompañado o no de otras nubes bajas.',
      '/': 'Nubes bajas invisibles por oscuridad, niebla, polvo, arena u otros fenómenos análogos.'
    },
    cm: { // 0515: nubes medias
      '0': 'Sin nubes medias (CM).',
      '1': 'Altostratus translucidus: en su mayor parte semitransparentes.',
      '2': 'Altostratus opacus o nimbostratus.',
      '3': 'Altocúmulus translucidus, a un solo nivel.',
      '4': 'Bancos de altocúmulus translucidus, a uno o varios niveles, que cambian continuamente de aspecto; frecuentemente lenticulares.',
      '5': 'Altocúmulus en bandas o capas que invaden progresivamente el cielo, volviéndose generalmente más espesos.',
      '6': 'Altocúmulus cumulogenitus: procedentes de la extensión de cúmulus.',
      '7': 'Altocúmulus en varias capas o capa opaca, sin invasión progresiva; o coexistentes con altostratus o nimbostratus.',
      '8': 'Altocúmulus castellanus o floccus.',
      '9': 'Altocúmulus generalmente a varios niveles en un cielo caótico.',
      '/': 'Nubes medias invisibles por oscuridad, fenómenos atmosféricos o una capa continua de nubes más bajas.'
    },
    ch: { // 0509: nubes altas
      '0': 'Sin nubes altas (CH).',
      '1': 'Cirrus fibratus, a veces uncinus, sin invadir progresivamente el cielo.',
      '2': 'Cirrus spissatus, castellanus o floccus; pueden parecer restos de la parte superior de un cumulonimbus.',
      '3': 'Cirrus spissatus cumulonimbogenitus: cirrus densos procedentes de la parte superior de cumulonimbus.',
      '4': 'Cirrus uncinus o fibratus, o ambos, que invaden progresivamente el cielo.',
      '5': 'Cirrus y cirrostratus, o cirrostratus solos, invadiendo progresivamente el cielo; velo continuo hasta 45° sobre el horizonte.',
      '6': 'Cirrus y cirrostratus, o cirrostratus solos, invadiendo el cielo; velo continuo superior a 45° sin cubrirlo totalmente.',
      '7': 'Cirrostratus que cubre completamente el cielo.',
      '8': 'Cirrostratus sin invasión progresiva y sin cubrir completamente el cielo.',
      '9': 'Cirrocúmulus predominantes, solos o acompañados por cirrus o cirrostratus.',
      '/': 'Nubes altas invisibles por oscuridad, niebla, polvo, arena o una capa continua de nubes más bajas.'
    }
  },
  soil: { // 0901 (no confundir con una tabla de estado del suelo distinta)
    '0': 'Superficie del suelo seca, sin grietas ni cantidad apreciable de polvo o arena suelta.',
    '1': 'Superficie del suelo húmeda.',
    '2': 'Superficie del suelo mojada, con agua estancada en charcos.',
    '3': 'Suelo inundado.',
    '4': 'Superficie del suelo helada.',
    '5': 'Hielo glaseado sobre la superficie.',
    '6': 'Polvo o arena secos que no cubren completamente el suelo.',
    '7': 'Fina capa de polvo o arena secos y sueltos que cubre todo el suelo.',
    '8': 'Capa mediana o espesa de polvo o arena secos y sueltos que cubre todo el suelo.',
    '9': 'Suelo extremadamente seco, con grietas.'
  },
  past: { // 4561
    '0': 'Nubes cubriendo la mitad del cielo o menos durante todo el período.',
    '1': 'Nubes cubriendo más de la mitad del cielo parte del período, y la mitad o menos durante el resto.',
    '2': 'Nubes cubriendo más de la mitad del cielo durante todo el período.',
    '3': 'Tempestad de arena o de polvo, o ventisca alta.',
    '4': 'Niebla, niebla helada o bruma espesa.',
    '5': 'Llovizna.',
    '6': 'Lluvia.',
    '7': 'Nieve o lluvia con nieve.',
    '8': 'Chaparrones.',
    '9': 'Tormentas, con o sin precipitación.'
  },
  tendency: { // 0200
    '0': 'En alza y luego en baja; presión final igual o superior a la de tres horas antes.',
    '1': 'En alza y luego estacionaria, o en alza y luego en alza más lenta.',
    '2': 'En alza, regular o irregular.',
    '3': 'En baja o estacionaria y luego en alza; o en alza seguida de un alza más rápida.',
    '4': 'Estacionaria: presión final igual a la de tres horas antes.',
    '5': 'En baja y luego en alza; presión final igual o inferior a la de tres horas antes.',
    '6': 'En baja y luego estacionaria, o en baja y luego en baja más lenta.',
    '7': 'En baja, regular o irregular.',
    '8': 'Estacionaria o en alza y luego en baja; o en baja seguida de una baja más rápida.'
  }
});
