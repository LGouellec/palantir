from transformers import pipeline

task = "text-classification"
model_id = "mrm8488/deberta-v3-ft-financial-news-sentiment-analysis"

classifier = pipeline(task, model_id)
text = """OpenAI and Anthropic are racing toward potentially record-breaking initial public offerings by the end of the year.\n\nAn inside look at the financials of both companies prior to\n\ncompleted earlier this year shows their Achilles’ heel: the soaring costs needed to train new artificial intelligence models.\n"""


result = classifier(text)
print(result)

# pip install transformers sentencepiece
# pip install torch