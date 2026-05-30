from transformers import pipeline

task = "text-classification"
model_id = "mrm8488/deberta-v3-ft-financial-news-sentiment-analysis"

classifier = pipeline(task, model_id)
text = """OpenAI and Anthropic are racing toward potentially record-breaking initial public offerings by the end of the year.\n\nAn inside look at the financials of both companies prior to\n\ncompleted earlier this year shows their Achilles’ heel: the soaring costs needed to train new artificial intelligence models.\n"""


result = classifier(text)
print(result)

# pip install transformers sentencepiece
# pip install torch

# France’s Answer to OpenAI Warns of Dangers of U.S. Tech Dominance\n\n**Author:** Sam Schechner\n**Published:** 2026-05-28T08:45:00.000Z\n**URL:** https://www.wsj.com/tech/ai/mistral-chases-ai-superintelligence-to-counter-u-s-dominance-b2a44fa1\n**Scraped:** 2026-05-28T13:57:59.122230\n**Word Count:** 78\n\n**Summary:** The French company’s CEO said its—and Europe’s—biggest obstacle to tech independence is the scale of investment necessary.\n\n---\n\nPARIS—French artificial-intelligence company Mistral AI says it is working as fast as it can on the moonshot race to develop what is called superintelligence—because Europe can’t afford to rely on U.S. tech giants.\n\nThe Paris-based startup has become Europe’s most prominent artificial-intelligence developer in part by playing to its home crowd:\n\nin Europe, independent of American tech companies and their Chinese competitors.\n\n\n