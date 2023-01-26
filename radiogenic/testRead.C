#include "TChain.h"
#include "TFile.h"
#include "TTree.h"
#include <iostream>

void testChain()
{
    TChain* tc = new TChain("event_tree");
    std::vector<std::string> files = {
        "./00/Ar42_rtd_slim_000000.root",
        "./01/Ar42_rtd_slim_000001.root" };

    // tchain expects const char* pointers to files
    for(const auto& str : files)
        tc->Add(str.c_str());
    std::cout << tc->GetEntries() << std::endl;

    // create histograms the same way you would normally with trees
    tc->Draw("pixel_x");

    // e.g.
    // cuts
    // TCut c1 = "(m_barEventsPreCal.m_ampl>0.0035)";
    // TCut c2 = Form("(m_barEventsPreCal.m_barID==%d)",barNum);
    // TCut c3 = "(m_barEventsPreCal.m_amplTrig<=0.070)";
    // draw to a specific histogram name
    // evtChain->Draw("osEvents.m_barEventsPreCal.m_ampl>>hta",c1+c2+c3);
    // barCal->set_spectrum(position,(TH1*)gDirectory->Get("hta"));

    delete tc;
}


void testRead()
{
    // open one of the root files
    TFile* tf = new TFile("./00/Ar42_rtd_slim_000000.root", "READ");
    TTree* tt = (TTree*)tf->Get("event_tree");
    int entries = tt->GetEntries();
    std::cout << "found entries: " << entries << std::endl;

    // get the branch objects
    int run = 0;
    int event = 0;
    double energy_deposit = 0.;
    // ALWAYS initialize pointers to something
    vector<int>* pixel_x = NULL;
    vector<int>* pixel_y = NULL;
    vector<vector<double>>* pixel_reset = NULL;
    vector<vector<double>>* pixel_tslr = NULL;

    // add the branches
    tt->SetBranchAddress("run", &run);
    tt->SetBranchAddress("event", &event);
    tt->SetBranchAddress("energy_deposit", &energy_deposit);
    tt->SetBranchAddress("pixel_x", &pixel_x);
    tt->SetBranchAddress("pixel_y", &pixel_y);
    tt->SetBranchAddress("pixel_reset", &pixel_reset);
    tt->SetBranchAddress("pixel_tslr", &pixel_tslr);

    // loop
    for(int i=0; i<tt->GetEntries(); ++i)
    {
        // this updates the address location of the branches
        tt->GetEntry(i);
        if(i%10 == 0)
        {
            std::cout << "Run: " << run << ", evt: " << event <<", energy_deposit: " << energy_deposit << std::endl;
            // print anything in the resets
            for(auto p : *pixel_tslr)
                for(auto d : p)
                    std::cout << d;
            for(auto p : *pixel_reset)
                for(auto d : p)
                    std::cout << d;
        }
    }


    delete tf;

    testChain();
}

