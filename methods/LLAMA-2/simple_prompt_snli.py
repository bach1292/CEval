import pandas as pd
from transformers import AutoTokenizer
import transformers
import torch
import time

def create_prompt(example, target_sentence = "premise"):
    example_map = {
        "neutral":{
            "premise": "Seven people are riding bikes on a sandy track.",
            "hypothesis": "The people are racing."
        },
        "entailment": {
            "premise": "Seven people are racing bikes on a sandy track.",
            "hypothesis": "People are riding bikes on a track."
        },
        "contradiction":{
            "premise": "Seven people are repairing bikes on a sandy track.",
            "hypothesis": "People are walking on a sandy track."
        }
    }

    # example_map = {
    #     "original_neutral": "The little boy in jean shorts kicks the soccer ball. A little boy is playing soccer outside.",
    #     "hypothesis_entailment": "The little boy in jean shorts kicks the soccer ball. A little boy is playing soccer..",
    #     "hypothesis_contradiction": "The little boy in jean shorts kicks the soccer ball. A little boy is playing cricket.",
    #     "premise_contradiction": "The little boy in jean shorts kicks the soccer ball in the house.	A little boy is playing soccer outside.",
    #     "premise_entailment": "The little boy in jean shorts kicks the soccer ball in the garden. A little boy is playing soccer outside."
    #     ""
    #     }
    orig_input = eval(example['orig_input'])
    sentence_1 = orig_input['sentence1']
    sentence_2 = orig_input['sentence2']
    orig_label = example['orig_pred']
    target_label = example['new_pred']
    if target_sentence == "premise":
        temp = f"""Premise: {example_map[orig_label]['premise']}\nHypothesis: {example_map["neutral"]['hypothesis']}"""
    else:
        temp = f"""Premise: {example_map["neutral"]['premise']}\nHypothesis: {example_map[orig_label]['hypothesis']}"""

#     template = f"""<s>[INST] <<SYS>>
# Given two sentences (premise and hypothesis) and their original relation, determine whether they entail, contradict, or are neutral to each other. Change the {target_sentence} with minimal edits to achieve the target relation from the original one. Do not make any unnecessary changes.
# <</SYS>>
# Original relation: {orig_label}
# {temp}
        
# Target relation: {target_label}
# Edited {target_sentence}:[/INST]{example_map[target_label][target_sentence]} </s><s>[INST] 
# Original relation: {orig_label}
# Premise: {sentence_1}
# Hypothesis: {sentence_2}
# Target relation: {target_label}
# Edited {target_sentence}:[/INST]"""
    template = f"""Request:  Given two sentences (premise and hypothesis) and their original relationship, determine whether they entail, contradict, or are neutral to each other. Change the {target_sentence} with minimal edits to achieve the {target_label} relation from the original one. Do not make any unnecessary changes.
Original relation: {orig_label}
{temp}
Target relation: {target_label}
<new>Edited {target_sentence}: {example_map[target_label][target_sentence]}</new>
######End Example#######

Request: Similarly, given two sentences (premise and hypothesis) and their original relationship, determine whether they entail, contradict, or are neutral to each other. Change the {target_sentence} with minimal edits to achieve the {target_label} relation from the original one.
Original relation: {orig_label}
[Start Original Text]
Premise: {sentence_1}
Hypothesis: {sentence_2}
[End Original Text]
Target relation: {target_label}
Do not make any unneccesary changes. Enclose the generated text within <new> tags. Do not add anything else. Make as few edits as possible.

"""
    template = [{
        "role": "user",
        "content": template
    }]
    return template
if __name__ == '__main__':

    llm_model = "meta-llama/Llama-2-7b-chat-hf"
    # llm_model = "tiiuae/falcon-40b-instruct"
    # sbert_model_name = "all-mpnet-base-v2"
    # dev_pairs = pd.read_csv("datasets/imdb/paired/dev_pairs.csv")
    # test_pairs = pd.read_csv("datasets/imdb/paired/test_paired.tsv", delimiter="\t")
    # train_pairs = pd.read_csv("datasets/imdb/paired/train_paired.tsv", delimiter="\t")
    # df_merge = pd.concat([train_pairs, test_pairs])
    # load dataset
    df = pd.read_csv("datasets/snli/expert/test_original.tsv", delimiter="\t")
    # df = df.dropna(axis=0)
    # df = df.groupby(['data_idx']).first()
    tokenizer = AutoTokenizer.from_pretrained(llm_model)
    llm_pipeline = transformers.pipeline(
        "text-generation",
        model=llm_model,
        torch_dtype=torch.float16,
        device_map="auto",
        tokenizer = tokenizer
    )

    #Negative	Long, boring, blasphemous. Never have I been so glad to see ending credits roll.	4
    #Positive	Long, fascinating, soulful. Never have I been so sad to see ending credits roll.
    #split sentiment pairs

    #generate sentiment embeddings for each sentiments:

    
    list_prompts = []
    # df_test = test_pairs
    #pick an instance
    # Specify the chunk size
    chunk_size = 5

    # Calculate the number of chunks
    num_chunks = len(df) // chunk_size + 1
    start_edited_pattern = r'\<new\>(.*?)(?:\<\/new\>)'
    start_time = time.time()
    for target_sentence in ["premise","hypothesis"]:
        list_texts = []
        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = (i + 1) * chunk_size
            chunk = df.iloc[start_idx:end_idx]
            list_chunk_prompts = []
            for index, example in chunk.iterrows():
                prompt = create_prompt(example, target_sentence)
                list_prompts.append(prompt)
                list_chunk_prompts.append(prompt)
            
            sequences = llm_pipeline(
                list_chunk_prompts,
                do_sample=True,
                top_k=50,
                num_return_sequences=1,
                max_new_tokens=64,
                eos_token_id=tokenizer.eos_token_id, 
                pad_token_id=tokenizer.eos_token_id
            )
            for seq in sequences:
                # print(seq[0]['generated_text']) 
                text = seq[0]['generated_text'].split("\n\n\n")[0]
                with open(r'raw_text_snli_llm.txt', 'a') as fp:
                    fp.write("[start]%s\n" % text)
                text_split = text.split(f"(Edited {target_sentence}):")
                if len(text_split) == 3:
                    contrast_text = text_split[2].split("\n\n")[0][1:]
                else:
                    #raise error
                    print("ERROR SUSPECT")
                    print(text)
                    try:
                        contrast_text = text_split[2].split("\n\n")[0][1:]
                    except IndexError:
                        print(text_split)
                list_texts.append(contrast_text)
        df[f"llama_{target_sentence}"] = list_texts
    end_time = time.time()
    df.to_csv("snli_llm.csv")
    duration = end_time - start_time
    print(duration)
    with open(r'duration.txt', 'w') as fp:
        fp.write("Duration: %s" % str(duration))
    