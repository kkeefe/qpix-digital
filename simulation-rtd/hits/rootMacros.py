import ROOT

def makeROOTFunctions():
    ROOT.gInterpreter.Declare(
    '''
    // helper function for branch
    int makeCount(const ROOT::VecOps::RVec<int>& branch_weight, const ROOT::VecOps::RVec<int>& branch_truth, const int& id)
    {
            int count = 0;
            for(int i=0; i<branch_weight.size(); ++i)
            {
                    if(branch_truth[i] == id)
                            count += branch_weight[i];
            }
            return count;
    }



    int defineBranch(const std::string& name, const ROOT::VecOps::RVec<int>& branch_weight, const ROOT::VecOps::RVec<int>& branch_truth)
    {
            int v;
            if(name == "Ar39"){
                    v = 1;

            }else if(name == "Ar42"){
                    v = 2;

            }else if(name == "Bi214"){
                    v = 3;

            }else if(name == "Co60"){
                    v = 4;

            }else if(name == "K40"){
                    v = 5;

            }else if(name == "K42"){
                    v = 6;

            }else if(name == "Kr85"){
                    v = 7;

            }else if(name == "Pb214"){
                    v = 8;

            }else if(name == "Po210"){
                    v = 9;

            }else if(name == "Rn222"){
                    v = 10;
            }else{
                    v = 0;
            }
            return makeCount(branch_weight, branch_truth, v);
    };
    ''')