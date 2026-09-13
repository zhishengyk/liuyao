"""Reviewed literary retellings share exclusion identity, not source text or outcomes."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from liuyao_mcp.canonical import load_document, resolve_spans
from liuyao_mcp.manual_ingest import build_database
from liuyao_mcp.retrieval import get_source, search_knowledge


ROOT = Path(__file__).resolve().parents[1]
GROUPS = {'zengshan-l10194-insurance-wealth': ('liuyao_zixiu_dxj.full.l4144.case',
                                      'liuyao_zixiu_dxj.full.l6344.case',
                                      'zengshan_pingshi_dxj-l10194-insurance-wealth',
                                      'zengshan_pingshi_dxj-l11666-insurance-repeat'),
 'liuyao_lifa_jinjie.event.p0248_career_industry': ('liuyao_lifa_jinjie.manual.p0248_career_industry',
                                                    'liuyao_xiangfa_jinjie_shang.manual.p0021_industry'),
 'zengshan-l7890-colleague-illness': ('liuyao_lifa_jinjie.manual.p0214_colleague_illness',
                                      'liuyao_zixiu_dxj.full.l2268.case',
                                      'liuyao_zixiu_dxj.full.l5656.case',
                                      'zengshan_pingshi_dxj-l7890-colleague-illness'),
 'liuyao_xiangfa_jinjie_xia-p0055-taobao-appeal': ('liuyao_lifa_jinjie.manual.p0223_taobao_appeal',
                                                   'liuyao_xiangfa_jinjie_shang.manual.p0060_shop_appeal',
                                                   'liuyao_xiangfa_jinjie_xia-p0055-taobao-appeal'),
 'zengshan-wealth-si-dingsi-jiji-huan': ('zengshan_buyi.manual.L12018C0000.case',
                                         'zengshan_pingshi_dxj-l11426-wealth-jiji-huan',
                                         'zengshan_pingshi_dxj.manual.l23146'),
 'zengshan-l5790-high-school-exam': ('liuyao_zixiu_dxj.full.l9264.case',
                                     'zengshan_pingshi_dxj-l10122-highschool-repeat',
                                     'zengshan_pingshi_dxj-l5790-high-school-exam'),
 'zengshan-l3830-wealth-empty': ('liuyao_lifa_jinjie.manual.p0057_wealth_zengshan',
                                 'zengshan_buyi.manual.L02438C0000.case',
                                 'zengshan_pingshi_dxj-l3830-wealth-empty'),
 'zengshan-l2946-rootless-illness': ('liuyao_lifa_jinjie.manual.p0204_self_illness',
                                     'zengshan_buyi.manual.L02114C0000.case',
                                     'zengshan_pingshi_dxj-l2946-rootless-illness'),
 'zengshan-l8378-long-illness': ('liuyao_zixiu_dxj.full.l6084.case',
                                 'zengshan_buyi.manual.L04650C0000.case',
                                 'zengshan_pingshi_dxj-l8378-long-illness'),
 'zengshan-l8506-mother-inlaw': ('zengshan_buyi.manual.L04778C0000.case',
                                 'zengshan_pingshi_dxj-l8506-mother-inlaw'),
 'zengshan-two-intents-chen-yichou-wealth-fatherinlaw': ('zengshan_buyi.manual.L07102C0000.case',
                                                         'zengshan_pingshi_dxj-l13294-two-intents',
                                                         'zengshan_pingshi_dxj-l13294-two-intents.cast2'),
 'liuyao_lifa_jinjie.event.p0215_uncle_critical': ('liuyao_lifa_jinjie.manual.p0215_uncle_critical',
                                                   'liuyao_xiangfa_jinjie_shang.manual.p0090_critical_uncle')}


# Completed screen buckets 11-20; retained four-cast chains stay source-specific.
GROUPS.update({'zengshan-father-near-illness-chen-wushen-qian-xiaoxu': ('liuyao_lifa_jinjie.manual.p0180_father_recent_illness',
                                                          'zengshan_buyi.manual.L02026C0000.case',
                                                          'zengshan_pingshi_dxj-l2642-father-illness'),
 'zengshan-l9174-coal-mine': ('liuyao_zixiu_dxj.full.l6164.case',
                              'zengshan_buyi.manual.L05366C0000.case',
                              'zengshan_pingshi_dxj-l9174-coal-mine'),
 'zengshan_pingshi_dxj.manual.l22070': ('zengshan_buyi.manual.L11490C0000.case',
                                        'zengshan_pingshi_dxj.manual.l22070'),
 'zengshan-l10474-lawsuit': ('zengshan_buyi.manual.L05882C0000.case', 'zengshan_pingshi_dxj-l10474-lawsuit'),
 'zengshan-l12242-border-assignment': ('zengshan_buyi.manual.L06666C0000.case',
                                       'zengshan_pingshi_dxj-l12242-border-assignment'),
 'zengshan_pingshi_dxj.manual.l20642': ('zengshan_buyi.manual.L10802C0000.case',
                                        'zengshan_pingshi_dxj.manual.l20642'),
 'zengshan_pingshi_dxj.manual.l20118': ('zengshan_buyi.manual.L10534C0000.case',
                                        'zengshan_pingshi_dxj.manual.l20118'),
 'liuyao_lifa_jinjie.event.p0081_girlfriend': ('liuyao_lifa_jinjie.manual.p0081_girlfriend',
                                               'liuyao_xiangfa_jinjie_shang.manual.p0141_girlfriend_fate'),
 'zengshan-south-trip-four-dayou-casts': ('zengshan_buyi.manual.L06858C0000.case',
                                          'zengshan_buyi.manual.L06858C0000.case.cast2',
                                          'zengshan_buyi.manual.L06858C0000.case.cast3',
                                          'zengshan_buyi.manual.L06858C0000.case.cast4',
                                          'zengshan_pingshi_dxj-l12838-south-trip-four',
                                          'zengshan_pingshi_dxj-l12838-south-trip-four.cast2',
                                          'zengshan_pingshi_dxj-l12838-south-trip-four.cast3',
                                          'zengshan_pingshi_dxj-l12838-south-trip-four.cast4'),
 'zengshan-l6838-daughter-poison': ('liuyao_zixiu_dxj.full.l4108.case',
                                    'zengshan_pingshi_dxj-l6838-daughter-poison')})

# Final screen 21-30: first/recast exam buckets share one event; source variants stay separate records.
GROUPS.update({'zengshan-l14438-cloud-sun': ('zengshan_buyi.manual.L07706C0000.case', 'zengshan_pingshi_dxj-l14438-cloud-sun'),
 'zengshan-l14790-rain-short': ('zengshan_buyi.manual.L07902C0000.case', 'zengshan_pingshi_dxj-l14790-rain-short'),
 'zengshan_pingshi_dxj.manual.l21102': ('zengshan_buyi.manual.L11038C0000.case',
                                        'zengshan_buyi.manual.L11038C0000.case.cast2',
                                        'zengshan_pingshi_dxj.manual.l21102',
                                        'zengshan_pingshi_dxj.manual.l21102.cast2'),
 'liuyao_lifa_jinjie.event.p0217_political_review': ('liuyao_lifa_jinjie.manual.p0217_political_review',
                                                     'liuyao_xiangfa_jinjie_shang.manual.p0145_political_review'),
 'zengshan-l11946-rain': ('zengshan_buyi.manual.L06578C0000.case', 'zengshan_pingshi_dxj-l11946-rain'),
 'zengshan_pingshi_dxj.manual.l23870': ('zengshan_buyi.manual.L12362C0000.case',
                                        'zengshan_pingshi_dxj.manual.l23870'),
 'zengshan-l11106-wife-illness': ('zengshan_buyi.manual.L06150C0000.case',
                                  'zengshan_pingshi_dxj-l11106-wife-illness'),
 'zengshan_pingshi_dxj.manual.l19338': ('zengshan_buyi.manual.L10158C0000.case',
                                        'zengshan_buyi.manual.L10158C0000.case.cast2',
                                        'zengshan_pingshi_dxj.manual.l19338',
                                        'zengshan_pingshi_dxj.manual.l19338.cast2'),
 'zengshan-l8638-official-promotion': ('zengshan_buyi.manual.L04906C0000.case',
                                       'zengshan_pingshi_dxj-l8638-official-promotion')})

# Two source versions of the same 2018-03-01 nightly chest pain event.
GROUPS['liuyao_lifa_jinjie.event.p0225_nightly_chest_pain'] = (
    'liuyao_lifa_jinjie.manual.p0225_nightly_chest_pain',
    'liuyao_xiangfa_jinjie_shang.manual.p0135_nightly_chest_pain',
)


# SHA-256 of the original ten protected fields, source identity and full text.
# Baseline: pre-v4 corpus DB 48b55e1e65adc80d50b20b47926305959d40cb573901d25fea366ef27c893a6b.
# Only L06150 changes: source L6178:C32-41 is disclosed after the first prediction.
# Its expected value was projected from that baseline, not a rebuilt-corpus snapshot.
# V5: update only 10 source-reviewed late-dialogue/own-cast role projections.
# The other 75 hashes remain unchanged; the two chest-pain hashes also match R04.
# The protected fields and full-source checks below remain unchanged.
PRESERVED_CASE_SHA256 = {
    'liuyao_lifa_jinjie.manual.p0225_nightly_chest_pain': '24c01cd1aaa2ccc91f24266c2ff4fd2a4849e3b244f4b844822334333f1a941d',
    'liuyao_xiangfa_jinjie_shang.manual.p0135_nightly_chest_pain': 'd3dda99a4949b86ceaed5d728a285076e009b9ca7881ac05c00eb5e85ebdbf39',
    'liuyao_lifa_jinjie.manual.p0057_wealth_zengshan': '15657196e1c40e2dc73e57582bf3a6b4306ca526c17a95de1a0a072d19ff9322',
    'liuyao_lifa_jinjie.manual.p0081_girlfriend': 'f3e609f4fd69720ac09996aa1b1ea0be1c8291ad90ff0127206779785f8a3a39',
    'liuyao_lifa_jinjie.manual.p0180_father_recent_illness': '7d294f18740d61178daba302cddff954e913f65f491e911e0303d2617edf228a',
    'liuyao_lifa_jinjie.manual.p0204_self_illness': 'a26b4f0d529c5cd8042f3720d7c903778871b37a50d661e72726fdee3084af38',
    'liuyao_lifa_jinjie.manual.p0214_colleague_illness': '1ef025ef9d9c7533a1af9d0ae575cc5d82d39097bfa6f1ac6b56a1fa80766dae',
    'liuyao_lifa_jinjie.manual.p0215_uncle_critical': 'be8ded760d2569b21af43ea759ab19213f342f842698ff8519b7254f99bd85dc',
    'liuyao_lifa_jinjie.manual.p0217_political_review': '01e89ccf811c3ea2ebd1543cdf516c6f3ac9827ea528272dfe2e200a0c5e1699',
    'liuyao_lifa_jinjie.manual.p0223_taobao_appeal': 'f3d1a96e1ca96ea05b5fed3ac4bde7e2d27dac4eb914051a837b63c9b915d48a',
    'liuyao_lifa_jinjie.manual.p0248_career_industry': '9d2edcf8c8ca25f73f415d689ceae31bddce464d16097e82ba6a5e804c96c976',
    'liuyao_xiangfa_jinjie_shang.manual.p0021_industry': '1104c6a951a3c7571b7934d21b1a2d8f2f5caa443f739ea534ee3902b7ece8dd',
    'liuyao_xiangfa_jinjie_shang.manual.p0060_shop_appeal': 'd05b3203a6d5ec6ca7ee90d02d177bbbb0c2cc4650fcbe9b2d25c6853e9a3124',
    'liuyao_xiangfa_jinjie_shang.manual.p0090_critical_uncle': '7dfcd7f27a138c6a4aec0138f02bec5f85ca933650e991a4d7fd7e01eb98a530',
    'liuyao_xiangfa_jinjie_shang.manual.p0141_girlfriend_fate': 'c7ec9ba6922368aa3108da327a42179519a507d28be7bba21b2102478ce02e26',
    'liuyao_xiangfa_jinjie_shang.manual.p0145_political_review': 'c643646a4cfcd9383f1c93d62885673ce285320edf9f0b4b0c0167767f7956e3',
    'liuyao_xiangfa_jinjie_xia-p0055-taobao-appeal': 'f4543e5b90ac839bc08770adce2d8aaa1818a0d625a5806180426845aeda4058',
    'liuyao_zixiu_dxj.full.l2268.case': '9a17a4ddf1aecb4082f3e86dd4f23d90c6ec988003beb3ae5407dda61fc5c4a3',
    'liuyao_zixiu_dxj.full.l4108.case': '6101ef756a88a556a24ec44c71c727e16e9595678b81f5eeb96ee7a368b93352',
    'liuyao_zixiu_dxj.full.l4144.case': '5f3388df9b31df2e87f5c77eb9106141e08463962f6e87604fc84385e88a17bc',
    'liuyao_zixiu_dxj.full.l5656.case': '2fa007eb6c2def11276f1353c20e2dcf59b0c040129b3914e8323b946a796888',
    'liuyao_zixiu_dxj.full.l6084.case': 'fd2ae88eae5b5de210ab65b665d459899a7743ceec412d86495dd53927e0c489',
    'liuyao_zixiu_dxj.full.l6164.case': '3bfa70301450849913477855fc7d52715c9afd84509b13acb5c1f34811f01c1b',
    'liuyao_zixiu_dxj.full.l6344.case': '385a6ddfdf610842a1b85cd07ff6ae73b48ef4ebe6315e0537cfc643e18ae4be',
    'liuyao_zixiu_dxj.full.l9264.case': '04e347d6fcf1aa4135110f4bfec6b51e98cf09f60111750c078bc93c3cda67a8',
    'zengshan_buyi.manual.L02026C0000.case': '66d065c6d56ba147107ae5d106b4fad79dad3599d20c22bdc1c96827b6d5ddca',
    'zengshan_buyi.manual.L02114C0000.case': 'ead07be9f9740ff1239a78acbc73a539090f00dbeccf88e8b77a53a27672f257',
    'zengshan_buyi.manual.L02438C0000.case': '4a88bb7cf8b5902a2fc271cede558a67fc60ce3339f64f6be7eafbe108bd41c4',
    'zengshan_buyi.manual.L04650C0000.case': 'a0994eac78c44cf0355be449e3e578a3397d5f16763fce74b71f1fc8574f7d0a',
    'zengshan_buyi.manual.L04778C0000.case': '1e18ee69a3e9b5d79762a5b39ea19f0adb252662018d826ce18d1acc9508cf36',
    'zengshan_buyi.manual.L04906C0000.case': '4a15ee214facd940fbbcac7a07b84b7e755c67ed007004a7b6a5b2e98c35c653',
    'zengshan_buyi.manual.L05366C0000.case': '914d0b441bda060a7c17d46519f7ccf1388945c936cad9ed41c047e525f73c57',
    'zengshan_buyi.manual.L05882C0000.case': '8955bae02c7a8a76b68d4d6e610960b585bdfe6848c7455904c0dbc615b6d301',
    'zengshan_buyi.manual.L06150C0000.case': 'b69fe163313809cd34cbdff276a846c0b0500457f38b68a161b1c06b8074b71a',
    'zengshan_buyi.manual.L06578C0000.case': 'a9490a762e0e1699bba283ed7310e8c26d8224ed3e9e3dca9dfc776e67b7f925',
    'zengshan_buyi.manual.L06666C0000.case': 'edaf296d24ab15a0ff9ff109235b0dd32c0c889648d95206689b095b9132ebb7',
    'zengshan_buyi.manual.L06858C0000.case': '01506f9745e6bc1e8270ea3899b225550a14c144fcbc565a1a4f19fed2f48588',
    'zengshan_buyi.manual.L06858C0000.case.cast2': '30c3f9881d81a5a392dc8e2a8cab965b187c9b2d30ded12367ed0037e2fc4e9a',
    'zengshan_buyi.manual.L06858C0000.case.cast3': '2ae3b826659ac694b05288a1a7ce4617ca754145ee7dae1f702e5906afe321d4',
    'zengshan_buyi.manual.L06858C0000.case.cast4': '05c6be4ae970422132d22232a006175a364c4dcfb53ff47c3773781d14d227eb',
    'zengshan_buyi.manual.L07102C0000.case': 'efdb4e3e75fc898d1413008b1744a441e1b5cb15d32091d28fa5d5c9ef35fe4c',
    'zengshan_buyi.manual.L07706C0000.case': 'b708a96557adc266e06901ccf49ecfd730ebbb9f7c08659e04e587803b2d44c3',
    'zengshan_buyi.manual.L07902C0000.case': '307bddc659c429ba2140292fc9e2c8093f9f5df940badcc04217ef15510efd81',
    'zengshan_buyi.manual.L10158C0000.case': '02956f87137b8126ccdcd47cb757c82e0fa4043fe8ffbc9e2a54257312d2b437',
    'zengshan_buyi.manual.L10158C0000.case.cast2': 'a0b95d28fc96c4ccc128892c05e3ba113e12d35d20d5f75bac7420cede767ae8',
    'zengshan_buyi.manual.L10534C0000.case': '66d2d9f33a3c60fba96e960f25ab88a4199ae7c39549ff37ec2495631d337a5f',
    'zengshan_buyi.manual.L10802C0000.case': '7dbff480327a0338f9cde8516fc689587e577fcd117fa6b6808c4129fd5f4ebf',
    'zengshan_buyi.manual.L11038C0000.case': '54374a139c3eff9a5f52b2c90d4ab6dac59520104583a7c127b49bae1185925f',
    'zengshan_buyi.manual.L11038C0000.case.cast2': '9d27518e40c6e28c342fd20facf4ece602bca0c4270bb3389a55ddc3947b7f34',
    'zengshan_buyi.manual.L11490C0000.case': 'ad8f3ddff58c270cb58131b7061c9cf48db7db6bed3a2ee44d83d2a65f1464d4',
    'zengshan_buyi.manual.L12018C0000.case': '34e48f7408f2aec4a7d93834e7c87043f77935f17620899a673b24190be4bb2a',
    'zengshan_buyi.manual.L12362C0000.case': '2b963062de0a0177c0bdbf4e47b6fe3105f68acbfa931bb4ff2602a312f022b6',
    'zengshan_pingshi_dxj-l10122-highschool-repeat': '01515a73b67622ee41c5176f57934d188b74eebde33817890b366b0ec7edc688',
    'zengshan_pingshi_dxj-l10194-insurance-wealth': 'fc2712d8d76af47ad8d6aa65d747f9d1a837ff2755466ce57be416d961a4784c',
    'zengshan_pingshi_dxj-l10474-lawsuit': '9eebbd1656cf69fa7152df26c1f53cf75da6f6aa083626430b22f0351e34bf39',
    'zengshan_pingshi_dxj-l11106-wife-illness': '5254566ea7e75e3566bee897e524cf86b5010ea0c6cf4b588924572245ecb45c',
    'zengshan_pingshi_dxj-l11426-wealth-jiji-huan': '729824d5368559bd251f7dc27fbfe57f7358a2585efa688fa7230b1553c17337',
    'zengshan_pingshi_dxj-l11666-insurance-repeat': 'd5cc9f4ffa8ef8b3c6defeee827bac37de3f045cffaf71a3e3ca30f2481572bb',
    'zengshan_pingshi_dxj-l11946-rain': 'deba0c3ce76bd0e39f28fc268ca27877ce7ee5455fa95ef587b4f15ffe14f5ba',
    'zengshan_pingshi_dxj-l12242-border-assignment': 'fa0ce16904bc18d1a4925ac2d6850ddc9f7b65b0102d1e7834625df1ce0307bc',
    'zengshan_pingshi_dxj-l12838-south-trip-four': 'ca4b3728e49c2b54202fb6a467d14af8356707046b89efe8eb0a9a6b21ca27fe',
    'zengshan_pingshi_dxj-l12838-south-trip-four.cast2': '18540ddb7f6d8f9533eb212df16db8702a1f46739f640e691782a250d344d1c1',
    'zengshan_pingshi_dxj-l12838-south-trip-four.cast3': '27ff6393bdbea57c6b5d44bec4ca0692a48a82414f696526805a84807429974a',
    'zengshan_pingshi_dxj-l12838-south-trip-four.cast4': 'bc9e18e566795bb781bcf1eccdc5031d933e2ec85ad64e1e6f027e76f813b347',
    'zengshan_pingshi_dxj-l13294-two-intents': 'cd202ad586ff1253ab171916e170c785b6b8054672d7713f081a7ee26d5ee471',
    'zengshan_pingshi_dxj-l13294-two-intents.cast2': '64ad050346c3d0a0f076467627ea990807fb05e30a4d73617321a5c3def586be',
    'zengshan_pingshi_dxj-l14438-cloud-sun': 'd406ec1f90efd5aec874885ca72d7774e3663231492d1c2b23180729ec790899',
    'zengshan_pingshi_dxj-l14790-rain-short': '9ff0d8c85174c3c6237df4317f64508d051f6be949efbf5ca610f179c65cd73f',
    'zengshan_pingshi_dxj-l2642-father-illness': '14de6f868f086009e9615c400b13bc525a8ede62ede09d56f23bd0df1d377ce0',
    'zengshan_pingshi_dxj-l2946-rootless-illness': '914b6865abd3e7938606d4dcda394512f05b9a53b5ab3f01348ea8f1b5e7a6e1',
    'zengshan_pingshi_dxj-l3830-wealth-empty': '65dc5dbcfadfa8ba07be814389ca8db0b588b1aaca35e1b51d83e1555bbd91d7',
    'zengshan_pingshi_dxj-l5790-high-school-exam': 'ee90d81171a6d706a08a9691d0cf6cf86a49cdb5fe4a268a42b4d5c9f1094185',
    'zengshan_pingshi_dxj-l6838-daughter-poison': 'f18d1a12e80bf8f22d0e6a6972e083f009f2ae6ed5aebbda0777e075c2e4b966',
    'zengshan_pingshi_dxj-l7890-colleague-illness': '27066a7d3b86ae3f329394a304aec75e987955a3e0374e47a709838b66ad7195',
    'zengshan_pingshi_dxj-l8378-long-illness': '5b66177af3b22effac7f08145bba58e8ad71aba07b52e2f3567840ed26a1d2d2',
    'zengshan_pingshi_dxj-l8506-mother-inlaw': '511c4bb38da9140c02ff8cc2d022205c662741e55489948753b7394f6d74d1e0',
    'zengshan_pingshi_dxj-l8638-official-promotion': '172ba19a63fc6f0e2bee8a54f257e50818a1ec9941e91710a024a6f34bb1d9a5',
    'zengshan_pingshi_dxj-l9174-coal-mine': '97552da7447d6cbdaad639f22fac708c1c2ecc37eab0d6e845ab0e6c05e1bb5d',
    'zengshan_pingshi_dxj.manual.l19338': '90f6911dfed497a437a2d5709e74367997993bdd1f73eaa8f71d1147f19ce8ea',
    'zengshan_pingshi_dxj.manual.l19338.cast2': '0e924dc323a01c4c6bc452a5133b1c1110175ec4e8ea64fb33d5709c3e548d0f',
    'zengshan_pingshi_dxj.manual.l20118': '8416118788df0257b31443e067681faae5d0fc0fe0ec89d7b88f7d47715c6a1a',
    'zengshan_pingshi_dxj.manual.l20642': 'e9a04c4668e52361763578f1e4415b0629e14cfa7d2a7c14e8a7db6521cbcfc0',
    'zengshan_pingshi_dxj.manual.l21102': '76eeb48a8ea3f17b9330c6948284a3eb8f9e3a684d6782d2d7415b8ff13c7ca8',
    'zengshan_pingshi_dxj.manual.l21102.cast2': '8bed7818e765cfd467fed43120c74f1d81d933336f33e82d37b42805d740dd3c',
    'zengshan_pingshi_dxj.manual.l22070': 'c16399d6d824c2119fd711448c41e70c7973c617657c66bdebb8e166a9765f81',
    'zengshan_pingshi_dxj.manual.l23146': '61a7cbacf805a588d7fa98099f632c5e124ae1ffc93e36954988b4d0f035f943',
    'zengshan_pingshi_dxj.manual.l23870': 'cf9617a4614cc2c90958586fd31f3f34b1053ece1fbcdb25934feab754654725',
}


def _preserved_payload_hash(case, source):
    fields = ('cast', 'question', 'outcome', 'quality', 'extraction', 'parts', 'review',
              'cast_sequence', 'related_case_ids', 'additional_casts')
    value = {key: case.get(key) for key in fields}
    value['source'] = {
        'source_id': source['source']['source_id'],
        'unit_id': case['unit_id'],
        'original_text': source['text'],
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf8')).hexdigest()


@pytest.fixture(scope='module')
def reviewed_database(tmp_path_factory):
    path = tmp_path_factory.mktemp('reviewed-event-groups')/'knowledge.sqlite'
    shared = ROOT/'data/knowledge.sqlite'
    before = hashlib.sha256(shared.read_bytes()).hexdigest() if shared.exists() else None
    build_database(ROOT, path)
    after = hashlib.sha256(shared.read_bytes()).hexdigest() if shared.exists() else None
    assert after == before
    return path


@pytest.mark.parametrize('event_id,members', GROUPS.items())
def test_reviewed_event_members_and_existing_recast_chain_are_complete(reviewed_database, event_id, members):
    with sqlite3.connect(reviewed_database) as db:
        actual = {row[0] for row in db.execute('SELECT id FROM cases WHERE duplicate_group=?', (event_id,))}
    assert actual == set(members)
    for member in members:
        case = get_source(member, max_chars=500000, db_path=reviewed_database)['structured_case']
        assert case['duplicate_group'] == event_id
        assert (case.get('event_id') or case['unit_id']) == event_id
        assert set(case['duplicate_candidates']) == set(members)-{member}


@pytest.mark.parametrize('event_id,members', GROUPS.items())
def test_excluding_any_reviewed_member_excludes_the_whole_event(reviewed_database, event_id, members):
    cases = [get_source(member, max_chars=500000, db_path=reviewed_database)['structured_case'] for member in members]
    nodes = ['manual_unit:'+case['unit_id'] for case in cases]
    options = dict(kind='case', outline_ids=nodes, limit=20, max_chars=500000,
                   retrieval_mode='bm25', db_path=reviewed_database)
    selected = search_knowledge('', **options)['items']
    assert len(selected) == int(any(case['quality']['status'] == 'eligible' for case in cases))
    for member in members:
        assert search_knowledge('', exclude_case_ids=[member], **options)['items'] == []


@pytest.mark.parametrize('first,second', [
    ('liuyao_lifa_jinjie.manual.p0078_work_selection', 'liuyao_xiangfa_jinjie_shang.manual.p0017_selection'),
    ('liuyao_lifa_jinjie.manual.p0138_future_path', 'liuyao_lifa_jinjie.manual.p0248_career_industry'),
    ('zengshan_pingshi_dxj-l8506-mother-inlaw', 'zengshan_pingshi_dxj-l13294-two-intents'),
    ('zengshan_buyi.manual.L04778C0000.case', 'zengshan_buyi.manual.L07102C0000.case'),
])
def test_suspected_or_different_narratives_remain_separate(reviewed_database, first, second):
    with sqlite3.connect(reviewed_database) as db:
        groups = [db.execute('SELECT duplicate_group FROM cases WHERE id=?', (member,)).fetchone()[0]
                  for member in (first, second)]
    assert groups[0] != groups[1]


def test_reviewed_sources_charts_quality_and_audits_are_preserved(reviewed_database):
    registry = {source['source_id']: source for source in map(json.loads,
                (ROOT/'data/canonical/sources.jsonl').read_text(encoding='utf8').splitlines())}
    documents, manifests = {}, {}
    members = {member for group in GROUPS.values() for member in group}
    assert set(PRESERVED_CASE_SHA256) == members
    for member in sorted(members):
        source = get_source(member, max_chars=500000, db_path=reviewed_database)
        case = source['structured_case']
        source_id = source['source']['source_id']
        if source_id not in documents:
            documents[source_id] = load_document(ROOT, registry[source_id])
            manifest = json.loads((ROOT/'data/manual_slices'/f'{source_id}.json').read_text(encoding='utf8'))
            manifests[source_id] = {unit['unit_id']: unit for unit in manifest['units']}
        unit = manifests[source_id][case['unit_id']]
        expected = resolve_spans(documents[source_id], unit['spans'])
        assert source['text'] == expected['exact_text']
        assert source['source']['sha256'] == documents[source_id].canonical_text_sha256
        assert _preserved_payload_hash(case, source) == PRESERVED_CASE_SHA256[member], member
    for source_id in documents:
        manifest = json.loads((ROOT/'data/manual_slices'/f'{source_id}.json').read_text(encoding='utf8'))
        for shard in manifest.get('assembled_from', []):
            assert hashlib.sha256((ROOT/shard['path']).read_bytes()).hexdigest() == shard['sha256']



def test_recovery_and_coal_timing_variants_are_not_normalized(reviewed_database):
    def text(case_id):
        return get_source(case_id, max_chars=500000, db_path=reviewed_database)['text']
    classic = text('zengshan_pingshi_dxj-l2642-father-illness')
    retelling = text('liuyao_lifa_jinjie.manual.p0180_father_recent_illness')
    assert '丑日起床' in classic and '丑日痊愈' not in classic
    assert '丑日痊愈' in retelling
    detailed = text('zengshan_pingshi_dxj-l9174-coal-mine')
    brief = text('liuyao_zixiu_dxj.full.l6164.case')
    assert '竟不见煤' in detailed and '竟不见煤' not in brief
    assert '后于亥年辰月挖出' in brief


def test_southbound_retellings_keep_both_four_cast_chains_and_date_wording(reviewed_database):
    originals = [('zengshan_pingshi_dxj-l12838-south-trip-four', '三四五月'),
                 ('zengshan_buyi.manual.L06858C0000.case', '三五月')]
    for unit_id, wording in originals:
        source = get_source(unit_id, max_chars=500000, db_path=reviewed_database)
        case = source['structured_case']
        assert wording in source['text']
        assert len(case['cast_sequence']) == 4 and len(case['additional_casts']) == 3
        expected = {unit_id, *[unit_id+f'.cast{index}' for index in (2, 3, 4)]}
        assert {entry['case_id'] for entry in case['cast_sequence']} == expected
        assert set(case['related_case_ids']) == expected-{unit_id}
        assert case['additional_casts'][1]['month_branch'] is None
        assert case['additional_casts'][2]['month_branch'] is None
        assert case['additional_casts'][2]['day_ganzhi'] is None
    # Eight records represent two literary versions of four casts, not eight historical casts.
    assert len(GROUPS['zengshan-south-trip-four-dayou-casts']) == 8



def test_provincial_exam_first_and_second_casts_keep_each_source_sequence(reviewed_database):
    for unit_id in ('zengshan_pingshi_dxj.manual.l21102', 'zengshan_buyi.manual.L11038C0000.case'):
        first = get_source(unit_id, max_chars=500000, db_path=reviewed_database)['structured_case']
        second = get_source(unit_id+'.cast2', max_chars=500000, db_path=reviewed_database)['structured_case']
        assert first['cast_index'] == 0 and second['cast_index'] == 1
        assert first['cast']['line_values'] == [1, 1, 2, 1, 1, 2]
        assert second['cast']['line_values'] == [3, 1, 2, 2, 2, 2]
        assert [entry['case_id'] for entry in first['cast_sequence']] == [unit_id, unit_id+'.cast2']
        assert first['related_case_ids'] == [unit_id+'.cast2']
        assert second['related_case_ids'] == [unit_id]
    assert len(GROUPS['zengshan_pingshi_dxj.manual.l21102']) == 4


def test_grandmother_recast_chart_variants_are_not_overwritten_by_event_identity(reviewed_database):
    pairs = [('zengshan_pingshi_dxj.manual.l19338', '归妹变震', [1, 3, 2, 1, 2, 2]),
             ('zengshan_buyi.manual.L10158C0000.case', '归妹变复', [1, 3, 2, 3, 2, 2])]
    for unit_id, title, values in pairs:
        source = get_source(unit_id, max_chars=500000, db_path=reviewed_database)
        second = get_source(unit_id+'.cast2', max_chars=500000, db_path=reviewed_database)['structured_case']
        assert title in source['text']
        assert second['cast']['line_values'] == values
        assert second['cast']['month_branch'] == '丑' and second['cast']['day_ganzhi'] == '庚子'
        assert second['related_case_ids'] == [unit_id]
    assert len(GROUPS['zengshan_pingshi_dxj.manual.l19338']) == 4
