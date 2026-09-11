"""Two-level question taxonomy. Unknown classification is never a common rule."""
import re

# IDs remain stable; aliases are evidence for an inferred label, not a confidence score.
DEFINITIONS = [
 ('relationship','姻缘感情','感情 婚姻 恋爱 姻缘 男友 女友 对象 缘分',[
  ('new_relationship','认识与择偶','相亲 桃花 脱单 找对象 情书'),('development','恋爱发展','谈朋友 恋爱 交往 缘分'),
  ('reconciliation','复合挽回','复合 复婚 和好 挽回'),('marriage','结婚与婚姻发展','结婚 再婚 婚期 婚姻 婚后'),
  ('separation','分手离婚','分手 离婚 分开 悔婚'),('intentions','对方态度','喜欢我 爱我 对我 真心 诚心')]),
 ('study','学业考试','考试 考学 升学 学习 成绩 学业',[
  ('exam','考试成绩','考试 考试成绩 考研 笔试 考公 公务员考试 资格考试 乡试 会试 科试 童试 赴试'),('admission','升学录取','录取 考上 升学 入学'),
  ('school_choice','择校专业','择校 选学校 选专业 转学 哪所学校 上学'),('progress','学业进展','学习 学业 成绩提高'),
  ('graduation','论文毕业','论文 毕业 答辩 送审')]),
 ('health','身体健康','病 身体 健康 手术 医院 症 腹痛 血压 寿命 寿元',[
  ('condition','身体状况','身体 健康 自测病 腹痛 血压 寿命 寿元 占寿'),('course','病情变化','病情 重病 近病 病发展 病趋势'),
  ('treatment','就医治疗','治疗 手术 医院 看病 医生 医药 住院 护工'),('recovery','恢复康复','康复 恢复 病何时好 出院'),
  ('safety','人身安危','安全 安危 车祸 受伤 跌伤'),
  ('relative','亲友健康','父亲病 母亲病 父亲的病 母亲的病 孩子病 儿子病 女儿病')]),
 ('job','事业工作','工作 求职 职位 上班 实习 事业 功名 官运 职业 行业 班主任',[
  ('job_search','求职面试','求职 应聘 面试 找工作'),('offer','录用入职','录用 入职 offer 聘用'),
  ('promotion','升职任用','升职 晋升 提拔 升官 升迁'),('change','工作变动','跳槽 辞职 离职 调动 换工作 换岗位'),
  ('stability','工作发展','工作前景 事业发展 工作发展 失业 裁员 下岗 辞退 班主任'),('relations','职场关系','同事关系 领导关系 职场关系 同事不理')]),
 ('wealth','财运经营','求财 财运 生意 买卖 投资 赚钱 钱财 店 创业',[
  ('business','经营创业','生意 开店 店铺 创业 经营 开铺 经商 卦馆'),('deal','买卖交易','买卖 交易 卖出 成交 贸易 卖掉 签单'),
  ('investment','投资收益','投资 股票 炒股 基金 外汇'),('debt','借贷回款','借钱 还钱 借款 欠款 回款 讨债'),
  ('income','收入财运','财运 求财 占财 收入 工资 奖金 利润 挣钱 获利 赚钱 摸奖 抽奖 中奖 奖券 彩票 管理财务')]),
 ('property','房产居家','房屋 房子 住房 买房 卖房 租房 搬家 装修',[
  ('purchase','买卖房产','买房 卖房 买房子 卖房子 购房 二手房'),('rental','租赁住房','租房 房租 租金 租这个 写字楼'),
  ('allocation','住房分配','分房 分配住房 申请住房 要住房 要房子'),
  ('moving','搬家迁居','搬家 迁居 新迁住宅'),('renovation','装修修造','装修 修造 建房'),('condition','房屋状况','房屋情况 房子情况 居住环境 风水')]),
 ('cooperation','合作签约','合作 合伙 签约 谈判 合同',[
  ('partner','合作对象','合作对象 合伙人 合作伙伴'),('negotiation','谈判协商','谈判 协商 商谈'),
  ('contract','签约合同','签约 合同 签字'),('progress','合作进展','合作进展 合作前景 合伙经营')]),
 ('children','孕育子女','怀孕 备孕 生育 胎儿 产期',[
  ('conception','备孕受孕','怀孕 备孕 受孕'),('pregnancy','孕期胎儿','胎儿 胎孕 孕期 保胎'),
  ('birth','生产产期','生产 分娩 产期 生孩子 临产')]),
 ('lost','失物寻人','丢失 失物 不见 失盗 遗失 走失 失联 离家 失踪 失禽 失畜 失牛 失马 失羊 失猪 失鸡',[
  ('belongings','失物寻找','丢失 失物 遗失 东西不见 丢了 丢哪里 钱包 失脱 失禽 失畜 失牛 失马 失羊 失猪 失鸡 家畜走失 牲畜丢失'),('theft','失盗追寻','被盗 失盗 小偷'),
  ('person','寻人失联','走失 失联 联系不上 找人 出走 离家 失踪 寻人')]),
 ('travel','出行行人','出行 出差 旅行 远行 行人 回来',[
  ('departure','出发出行','出行 出差 出发 出国 出门'),('journey','旅途情况','旅行 旅途 路上 顺利到达'),
  ('return','归期消息','回来 归期 行人 回家 何时到 何日回 未归')]),
 ('lawsuit','诉讼纠纷','诉讼 法院 官司 强制执行 纠纷 拘留 扣留 羁押 入狱 出狱 被捕 获释',[
  ('litigation','诉讼裁判','官司 诉讼 起诉 判决 法院 官事 重罪 被讼 拘留 扣留 羁押 入狱 出狱 被捕 获释'),('enforcement','执行追偿','强制执行 执行款 赔偿'),
  ('settlement','调解和解','和解 调解'),('dispute','纠纷争议','纠纷 争议 争执')]),
 ('objects','物品事务','物品 购买 修理 快递 物件',[
  ('purchase','购买选择','购买 买车 选购'),('quality','品质状态','质量 好用 真伪 真假 坏了'),
  ('repair','维修处理','维修 修理 修好'),('delivery','寄送交付','快递 寄送 到货 交付 发货 寄的')]),
 ('weather','天气农事','天气 下雨 降雨 农事 种植 养殖',[
  ('weather','天气变化','天气 下雨 降雨 晴天'),('planting','种植收成','种植 收成 田禾 农作物'),
  ('livestock','养殖牲畜','养殖 牲畜 鱼塘')]),
 ('affairs','日常事务','办事 运势 比赛 评选',[
  ('assistance','求助办事','帮忙 办一件事 谒贵 求人'),('approval','证照审批','许可证 批准 审批 财政局'),
  ('competition','比赛评选','比赛 拿奖 获奖 作品 选中'),('service','日常服务','理发 发型 美容'),
  ('publication','文稿出版','出版 发表 审稿 书稿'),
  ('fortune','整体运势','流年 运势 终身 命运 前程')])]

GENERAL = re.compile(r'用神|元神|忌神|仇神|六亲|月建|日辰|旺衰|旬空|月破|动爻|变爻|进神|退神|三合|六合|六冲|生克|神煞|卦身|应期')
GENERAL_CHAPTER = re.compile(r'^(?:第[一二三四五六七八九十百\d]+章\s*)?[冲合]$')
BACKGROUND_CONTEXT = re.compile(r'工作单位|男友|女友|合伙人|合作伙伴|医院|医生|班主任|帮忙')
QUESTION_EVENT = re.compile(r'(?<!预)[占测问](?!得|者|卦|之|题|[，,。；;：:\s]|$)')
REFERENCE_QUESTION = re.compile(r'[占测问](?:何|几|什么时候|是否|能否|可否|她|他|它|其|此|这|该|能|可|会|有无)')
STATUS_QUESTION = re.compile(r'[占测问](?:目前|现在|当前|最近|近来)?(?:人身)?(?:安危|安全|平安|下落|去向|吉凶|成败|得失|进展|结果|前景|情况|近况|现状|消息)')
ADDITIONAL_EVENT = re.compile(r'(?:另外|同时|还有|也|再|又|兼|并)(?:想|要|想要)?$')
CAUSAL_EVENT = re.compile(r'影响|导致|耽误|妨碍|阻碍')
ACTIVITY_TIME = re.compile(r'(?:看病|就医|上班|工作|学习|上学|出差|出行|旅行|购物|吃饭|洗澡)(?:的时候|时候|之时|时)(?!间|期|段|刻)')
WEATHER_QUESTION = re.compile(r'[占测问](阴晴|晴雨|风雨|顺风|逆风|晴|雨|雪|风|阴)(?=$|[，,。；;？！?]|何|几|能|会|可|否|不|有|无|停|止|起|下|转|来|去)')
SCHEMA = '''CREATE TABLE topics(id TEXT PRIMARY KEY,parent_id TEXT,title TEXT NOT NULL);
CREATE TABLE evidence_classification(evidence_id TEXT PRIMARY KEY,scope TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE evidence_topics(evidence_id TEXT NOT NULL,topic_id TEXT NOT NULL,
    PRIMARY KEY(evidence_id,topic_id));
CREATE INDEX topic_evidence ON evidence_topics(topic_id,evidence_id);'''


def nodes():
    result = []
    for root, title, aliases, children in DEFINITIONS:
        result.append({'id':root,'parent_id':None,'title':title,'aliases':aliases.split()})
        result += [{'id':root+'/'+key,'parent_id':root,'title':label,'aliases':words.split()}
                   for key,label,words in children]
    return result


def topic_matches(text, catalog):
    found = []
    weather = [match[1] for match in WEATHER_QUESTION.finditer(text)]
    for node in catalog:
        matched = [a for a in node['aliases'] if a.lower() in text]
        if node['id'] in ('weather','weather/weather'):
            matched = list(dict.fromkeys(matched + weather))
        if matched:
            found.append({'id':node['id'],'matched_terms':matched,
                          'score':sum(len(a) for a in matched)})
    return found


def classify(text):
    text = text.lower()
    # 收回来 describes recovery of something, not a person's return journey.
    text = text.replace('收回来', '收回')
    text = text.replace('借出去的钱', '借款')
    # 官鬼不见 describes a chart, not a missing person/object.
    text = re.sub(r'(?:(?:官鬼|妻财|用神|元神|忌神|仇神|飞神|伏神)(?:爻)?|(?:父母|兄弟|子孙)爻)(?:不见|不现|不上卦)', '', text)
    # A role/place is useful when no event is stated; explicit events retain all
    # their labels, including separate work, health, and other matters together.
    catalog, parts, context = nodes(), [], []
    event = QUESTION_EVENT.search(text)
    if event and event.start() and not CAUSAL_EVENT.search(text):
        prefix, question = text[:event.start()], text[event.start():]
        prefix_roots = {hit['id'].split('/')[0] for hit in topic_matches(prefix,catalog)}
        question_roots = {hit['id'].split('/')[0] for hit in topic_matches(question,catalog)}
        # A named question after a narrative preface establishes the event.
        # Status/reference follow-ups need their earlier event; they do not name
        # an independent event like "问比赛名次" or "测雨何时停".
        if (prefix_roots-question_roots and question_roots
                and not REFERENCE_QUESTION.match(question)
                and not STATUS_QUESTION.match(question)
                and not ADDITIONAL_EVENT.search(prefix)
                and not ('lost' in prefix_roots and 'travel' in question_roots)):
            context.append(prefix.rstrip(' ，,。；;'))
            text = question
    for clause in re.split(r'以及|另外|同时|还有|[；;]|和(?!好|解)|及(?!格)', text):
        if not CAUSAL_EVENT.search(clause):
            without_activity = ACTIVITY_TIME.sub('',clause)
            if without_activity != clause and topic_matches(BACKGROUND_CONTEXT.sub('',without_activity),catalog):
                context.extend(ACTIVITY_TIME.findall(clause))
                clause = without_activity
        event_text = BACKGROUND_CONTEXT.sub('', clause)
        if topic_matches(event_text,catalog):
            parts.append(event_text)
            context.extend(BACKGROUND_CONTEXT.findall(clause))
        else:
            parts.append(clause)
    event_text = ' '.join(parts)
    found = topic_matches(event_text,catalog)
    found.sort(key=lambda n:(-n['score'],n['id']))
    paths = list(dict.fromkeys(n['id'] for n in found))
    roots = list(dict.fromkeys(p.split('/')[0] for p in paths))
    # Combine the evidence for an event across its parent and specific subtopics;
    # a single long role word (合伙人) must not outweigh explicit detention/诉讼.
    root_scores = {root: sum(n['score'] for n in found if n['id'].split('/')[0] == root) for root in roots}
    roots.sort(key=lambda root: (-root_scores[root], root))
    primary = roots[0] if roots else None
    result = {'status':'inferred_from_text' if found else 'unknown', 'topic':primary,
              'topic_ids':paths, 'roots':roots, 'evidence':found}
    if context:
        result['background_context'] = context
    return result


def classify_rule(chapter, theory_text, case_questions, method):
    if method == 'xiangfa':
        return {'status':'scene_indexed','scope':'scene','topic_ids':[],'roots':[],'evidence':[]}
    result = classify(chapter)
    result['basis'] = 'chapter'
    if not result['topic_ids'] and theory_text.strip() and (GENERAL.search(chapter) or GENERAL_CHAPTER.fullmatch(chapter)):
        result.update(scope='common',status='inferred_from_general_heading')
        return result
    if not result['topic_ids']:
        explicit = ' '.join(re.findall(r'(?:占|测|问|预测|对于|关于)[^。\n]{0,45}', theory_text))
        result = classify(explicit)
        result['basis'] = 'explicit_application_text'
    if result['topic_ids']:
        result['scope'] = 'subtopic' if any('/' in t for t in result['topic_ids']) else 'topic'
    elif not theory_text.strip() and case_questions:
        result = classify(' '.join(case_questions))
        result.update(scope='example',basis='case_questions')
    else:
        result['scope'] = 'unknown'
    return result


def resolve(topic=None, subtopic=None):
    catalog = nodes()
    known = {n['id']:n for n in catalog}
    if topic and topic not in known:
        topic = next((n['id'] for n in catalog if not n['parent_id'] and
                      (topic == n['title'] or topic in n['aliases'])), topic)
    if subtopic and subtopic not in known:
        candidates = [n['id'] for n in catalog if n['parent_id'] and
                      (subtopic == n['id'].split('/')[1] or subtopic == n['title']) and
                      (not topic or n['parent_id']==topic)]
        if len(candidates)==1:subtopic=candidates[0]
    if topic and (topic not in known or known[topic]['parent_id']):
        raise ValueError('未知大类，请先get_topics')
    if subtopic:
        if subtopic not in known or not known[subtopic]['parent_id']:
            raise ValueError('未知小类，请先get_topics')
        parent=known[subtopic]['parent_id']
        if topic and topic != parent:raise ValueError('小类不属于指定大类')
        topic=parent
    return topic,subtopic


def tier(classification, topic, subtopic, include_common=True):
    if classification.get('scope') == 'common' and not include_common:return None
    if not topic:return 0
    roots=classification.get('roots',[])
    if topic in roots:
        if subtopic and subtopic in classification.get('topic_ids',[]):return 0
        return 1 if subtopic else 0
    if classification.get('scope') == 'common':return 2 if include_common else None
    if not roots:return 3  # Unknown is a fallback, never relabelled common.
    return None
