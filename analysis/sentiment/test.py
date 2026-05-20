from transformers import pipeline

task = "text-classification"
model_id = "mrm8488/deberta-v3-ft-financial-news-sentiment-analysis"

classifier = pipeline(task, model_id)
text = """President Trump is confronting a challenge with Iran’s nuclear program that is partly of his own making: a mountain of highly enriched uranium that Tehran has refused to hand over despite two months of war.
Iran accumulated fissile material after Trump pulled out of a nuclear deal in 2018. It then accelerated its program, producing the near-bomb-grade material, during the Biden and second Trump administrations, according to data from the United Nations’ atomic agency.

Now an important war aim for Trump is ensuring that Tehran doesn’t have the capability to develop a nuclear weapon, but Iran has refused to accept Washington’s terms. Neither the economic pressure campaign from Trump’s first term nor U.S.-Israeli military strikes that were carried out in June and then renewed in February have forced Iran to abandon its uranium stockpile or halt its nuclear efforts.

On Monday, Trump said he was holding off on further military action against Iran because there is “a very good chance” a deal can be reached in the stop-and-start diplomacy the White House has conducted since he returned to the White House. Few experts are so confident."""

result = classifier(text)
print(result)

# pip install transformers sentencepiece
# pip install torch