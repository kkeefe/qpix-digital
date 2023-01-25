import os
import sys
import ROOT

ROOT.EnableImplicitMT(True)
# ROOT.gInterpreter.GenerateDictionary("ROOT::VecOps::RVec<vector<double>>", "vector")
# ROOT.gInterpreter.Declare("ROOT::VecOps::RVec<vector<double>> bla;")
# ROOT.gSystem.Load("liblibs.so")
# ROOT.gSystem.Load("libQPixRTD.so")

def getRDFs(isofs):
    """
    function to create a dictionary of RDF's based on the isotope files handed to it
    """
    iso_rdfs = {}
    for isotope, files in isofs.items():
        iso_rdfs[isotope] = ROOT.RDataFrame("event_tree", files)

    return iso_rdfs

def getIsotopeFiles(fs):
    """
    this function should be able to return a RDF that corresponds to the preprend
    isotope
    """
    isotopes = set()

    # file structor is: /path/to/dir/00/iso_name_file.root
    # therefore rpartition for / and then partition on _ to separate for iso
    for f in fs:
        isotope = f.rpartition("/")[2].partition("_")
        isotopes.add(isotope[0])

    # create a dictionary of isotope to files
    isotope_files = {}
    for iso in isotopes:
        isotope_files[iso] = [f for f in fs if iso in f]

    return isotope_files


def getRootFiles():
    """
    this function should walk the radiogenic directory and spit back the file path
    of all ROOT files:
    """

    files = []
    for rs, ds, fs in os.walk("./radiogenic"):
        f = [f for f in fs if "root" in f]
        if f:
            f = [os.path.join(rs, f) for f in f ]
            files.extend(f)

    return files

def defineFilters(rdfs, xmin=80, xmax=120, ymin=80, ymax=120):
    """
    function takes in rdf dictionary and should define timestamp branch ond then filter
    on data to get the interesting events, or events that have timestamps at all
    """

    ROOT.gInterpreter.Declare("std::string isoname;")
    for iso, rdf in rdfs.items():
        ROOT.isoname = iso;
        rdfs[iso] = rdf.Define("Isotope", f'return isoname;')\
                       .Filter(f"""bool found = false; 
                                 for(auto x : pixel_x) 
                                   if(x > {xmin} && x < {xmax}) found = true; 
                                 return found;""")\
                       .Filter(f"""bool found = false; 
                                 for(auto y : pixel_y) 
                                   if(y > {ymin} && y < {ymax}) found = true; 
                                 return found;""")

    return rdfs

def main():
    files = getRootFiles()
    print(files[:10], len(files))

    isotopes = getIsotopeFiles(files)
    for k,v in isotopes.items():
        print(k, len(v))

    rdfs = getRDFs(isotopes)

    # figure out the interesting branch names in the tree
    branchNames = set()

    rdfs = defineFilters(rdfs)

    npData = {}
    for iso, rdf in rdfs.items():
        print(iso, rdf.GetColumnNames())
        # for col in rdf.GetColumnNames():
            # print(col, rdf.GetColumnType(col))
        # rdf.Snapshot("event_tree", f'./scripts/output_data/{iso}_sim.root')

        print(rdf.Count().GetValue())
        h1 = rdf.Histo1D("event")
        h1.Draw()
        npData[iso] = rdf.AsNumpy(["pixel_x", "pixel_y", "pixel_tslr", "pixel_reset", "run", "event"])

    for iso, data in npData.items():
        for col, npd in data.items():
            print(iso ,col, len(npd))

    input("waiitng..")


if __name__ == "__main__":
    main()
