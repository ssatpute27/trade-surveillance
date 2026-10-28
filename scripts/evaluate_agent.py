"""Run the offline evaluator; never supply this output to the investigator."""
import json
from app.evaluation import evaluate
from app.config import ROOT

def main():
    result=evaluate();path=ROOT/'evals/latest_results.json';path.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2))

if __name__=='__main__':main()
