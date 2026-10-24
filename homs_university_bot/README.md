# بوت جامعة حمص

بوت تيليغرام يجيب طلاب جامعة حمص من **إجابات راجعها إنسان واعتمدها** فقط.
إذا ما لقى دليلاً كافياً يقول ذلك ويسجّل السؤال. ما بيخترع نظاماً أو موعداً أو رقم مادة.

هذا الإصدار الأول محلي، ومن دون نموذج لغوي مدفوع ومن دون بطاقة رسوميات.

## القرار المعماري

ثلاث هويات منفصلة:

| السجل | المعنى |
| --- | --- |
| Question ID | صياغة سؤال محفوظة أو صيغة معتمدة |
| Intent ID | المعنى المشترك بين أكثر من صياغة |
| Answer ID | جواب مُراجَع لسياق معيّن وإصدار من القاعدة |

صيغ كثيرة ممكن تشير إلى قصد واحد. والقصد الواحد ممكن يكون له أكثر من جواب حسب الكلية أو نظام الدراسة أو تاريخ السريان.

تفاعل الطالب (نصّه، درجة المطابقة، ملاحظته) يُحفظ في جدول مستقل. ملاحظة «مفيد» أو «غير صحيح» **ما بتعدّل الجواب ولا تنشر جواباً جديداً**. ما في تعلم تعزيزي في هذا الإصدار. التحسين يتم بمراجعة بشرية ثم قياس أثرها على المطابقة.

المطابقة الحالية لفظية (`difflib` + تقاطع الكلمات). الدرجة علامة تشابه بين 0 و 1، **وليست احتمالاً**. عتباتها في البيئة:

- `HU_MATCH_AUTO` الافتراضي `0.84`: تطابق يُعتمد إذا ابتعد عن القصد التالي بمقدار `HU_MATCH_MARGIN` (الافتراضي `0.06`).
- `HU_MATCH_CLARIFY` الافتراضي `0.62`: تحتها يُعتبر السؤال غير مطابق. بين العتبتين، أو إذا اقترب قصدان، تظهر أزرار توضيح.

التضمينات الدلالية واستدعاء نموذج لغوي موجودان كنقاط استبدال فقط (`homs_bot/similarity.py` و `homs_bot/llm.py`) وما بيشتغلان الآن.

## السياق وسياسة الجواب

البوت يجمع بالأزرار: الكلية، السنة، نظام الدراسة، والاختصاص إذا كانت الكلية لها اختصاصات محفوظة في `data/catalog.json`.
ما بيسأل متابعة إلا إذا في حقل ناقص **يغيّر الجواب المعتمد**. إذا النص نفسه بكل الحالات ما بيسأل.

يُعرض الجواب فقط إذا كان الجواب **والمصدر** بحالة `approved`، وضمن تاريخ السريان، وما بيتعارض مع سياق الطالب. المسودة والمتقاعد والمصدر غير المعتمد ما بينعرضوا. إذا تعارض جوابان معتمدان بنفس درجة التحديد، البوت ما بيختار وبيعلّم الحالة للمراجعة.

## البيانات التجريبية

ملف `data/synthetic_demo.json` أمثلة **مصطنعة** مكتوب عليها ذلك. أداة `seed.py` تجبر `is_synthetic = 1` مهما كان محتوى الملف.

- الوضع الطبيعي (`HU_ALLOW_SYNTHETIC=0`) يتجاهلها بالكامل.
- وضع التجربة (`HU_ALLOW_SYNTHETIC=1`) يعرضها مع تنبيه أنها ليست أنظمة جامعة حمص وليست إرشاداً رسمياً.

لا تضع أنظمة الجامعة الحقيقية داخل هذا الملف.

أسماء الكليات والاختصاصات في `data/catalog.json` خيارات تنقّل فقط، وليست قواعد تسجيل.

## التثبيت

من مجلد `homs_university_bot`:

```bash
cd homs_university_bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

ثم عدّل `.env`:

- `TELEGRAM_BOT_TOKEN` من BotFather. اتركه فارغاً إذا بدك تشغّل الاختبارات وأوامر الإدارة فقط.
- `HU_ADMIN_KEY` مفتاح محلي طوله 12 محرفاً على الأقل. من دونه أوامر الإدارة بترفض تشتغل.
- `HU_ADMIN_IDS` أرقام حسابات تيليغرام المسموح لها تشوف `/admin`، مفصولة بفاصلة. الأمر ما بيعدّل المحتوى؛ التعديل من الجهاز فقط.
- `HU_ALLOW_SYNTHETIC=0` للتشغيل العادي.

لا ترفع `.env` ولا ملف `data/*.sqlite` ولا رمز البوت. الاثنان مضافان إلى `.gitignore`.

## الاختبار

```bash
cd homs_university_bot
source .venv/bin/activate
python -m unittest discover -s tests -v
```

الاختبارات تغطي: اختيار السياق وتعديله وحذفه، المطابقة الغامضة، الجواب غير المعتمد، القاعدة المتقاعدة وسجل الإصدارات، حجب البيانات المصطنعة، والملاحظات التي لا تغيّر النص.

## تشغيل البوت

```bash
cd homs_university_bot
source .venv/bin/activate
python -m homs_bot
```

إذا الرمز ناقص، العملية بتقف برسالة واضحة وما بتصل بتيليغرام. المحرك نفسه يشتغل من دون الرمز، كما في الاختبارات.

أوامر الطالب داخل تيليغرام: `/start`، `/context`، `/delete_my_data`، `/help`. الأمر الأخير يحذف السياق وسجل أسئلة هذا الحساب على البوت. ما منخزّن الاسم.

في كل مستخدم حد مؤقت، افتراضياً 8 رسائل كل 30 ثانية (`HU_RATE_LIMIT_COUNT` و `HU_RATE_LIMIT_WINDOW`). السجلات ما لازم تحتوي الرمز ولا مفتاح الإدارة.

## أوامر الإدارة

تُشغَّل على الجهاز الذي فيه قاعدة SQLite، وبعد ضبط `HU_ADMIN_KEY`.

```bash
cd homs_university_bot
source .venv/bin/activate
export HU_ADMIN_KEY='ضع-مفتاحا-طويلا'

python -m homs_bot.admin_cli intent-list
python -m homs_bot.admin_cli intent-add --code example_intent --title "عنوان" --status draft
python -m homs_bot.admin_cli question-add --intent example_intent --wording "كيف أسأل؟" --status draft
python -m homs_bot.admin_cli question-approve --id q_...
python -m homs_bot.admin_cli source-add --title "عنوان المصدر" --issuer "الجهة" --reference "https://example.test/rule" --article "المادة 1" --effective-from 2026-01-01 --status approved
python -m homs_bot.admin_cli answer-add --intent example_intent --source src_... --body "نص الجواب" --status draft
python -m homs_bot.admin_cli answer-retire --id ans_...
python -m homs_bot.admin_cli answer-history --intent example_intent
python -m homs_bot.admin_cli review-unmatched
python -m homs_bot.admin_cli review-feedback
python -m homs_bot.admin_cli review-map --interaction 12 --intent example_intent
python -m homs_bot.admin_cli review-resolve-feedback --id 3 --note "شُوهدت من دون تعديل النص"
python -m homs_bot.admin_cli review-dismiss --interaction 12
python -m homs_bot.admin_cli delete-context --telegram-id 123456
python -m homs_bot.admin_cli seed-demo
```

`question-add` و `answer-add` و `intent-add` تنشئ مسودة إلا إذا طُلبت حالة أخرى صراحة. ما بيصير اعتماد جواب إذا مصدره مو معتمد. `review-map` ينسخ صياغة الطالب إلى **مسودة**، وما بتدخل المطابقة قبل `question-approve`.

`seed-demo` يحمّل الأمثلة المصطنعة إلى قاعدة `HU_DB_PATH` (الافتراضي `data/homs_bot.sqlite`).

## تجربة المحرك من دون تيليغرام

```bash
cd homs_university_bot
python3 -m homs_bot.lab_cli ask <<'JSON'
{"userId": 1, "text": "كيف أوقف تسجيلي", "facultyCode": "informatics", "academicYear": "2", "studySystem": "regular", "specializationCode": "software", "allowSynthetic": true}
JSON
```

مع `"allowSynthetic": false` نفس السؤال يبقى بلا جواب رسمي، لأن السجل التجريبي محجوب.

المختبر في واجهة المعاينة يستدعي هذا المحرك نفسه. هو ليس قناة رسمية، ومستخدمه المحلي ثابت وليس حساب تيليغرام.

## تخطيط الملفات

```text
homs_bot/text_norm.py      تطبيع العربية مع الإبقاء على النص الأصلي
homs_bot/matching.py       من الصيغ إلى قصد واحد أو أزرار توضيح
homs_bot/answering.py      اختيار الجواب الساري أو طلب حقل ناقص
homs_bot/pipeline.py       ترتيب الخطوات وتسجيل التفاعل
homs_bot/db.py             SQLite
homs_bot/handlers.py       أزرار تيليغرام
homs_bot/admin_cli.py      إدارة محلية
homs_bot/lab_cli.py        واجهة JSON للمختبر
data/synthetic_demo.json   أمثلة مصطنعة
```

## ما ليس جاهزاً بعد

- ما في أنظمة حقيقية مدخلة لجامعة حمص. لا تعتمد أي جواب تجريبي.
- البوت ما بيشتغل على تيليغرام قبل ما يوضع `TELEGRAM_BOT_TOKEN` على الجهاز الذي يشغّله.
- ما في لوحة ويب للإدارة. الاعتماد يتم من أوامر الجهاز حتى ما يننشر جواب من المتصفح.
- المطابقة اللفظية بتفوّت صيغاً بعيدة. الخطوة الجاية: مجموعة تقييم من أسئلة حقيقية مُراجَعة، ثم قياس إذا كانت التضمينات تستاهل الإضافة. مو قبل هالقياس.
