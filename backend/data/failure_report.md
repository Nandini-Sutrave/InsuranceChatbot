# Failure Diagnosis Report

This report analyzes every failed query on the human benchmark.

## Query 1: Are spa treatments and nature cures covered by the health policy?
- **Expected Document**: HDFC
- **Expected Heading**: Exclusions
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4775 | 11.7623 | 0.3333 | 1.25 | 0.0000 | 0.4856 |
| 2 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > the Policy Period | 0.0000 | 0.0000 | 0.2222 | 1.00 | 0.0000 | 0.1765 |
| 3 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > D.1 Domestic Help/Staff Indemnity | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 4 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4754 | 12.1281 | 0.3333 | 1.25 | 0.0000 | 0.4590 |
| 5 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4769 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.4093 |
| 6 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Treatment) or Section C.7 (Modern Treatments) or Section C.8 | 0.4715 | 13.1599 | 0.2222 | 1.25 | 0.0000 | 0.4080 |
| 7 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 8 | D. OPTIONAL COVERS > (Inpatient Hospitalization Treatment) or Section C.4 (Day Care | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 8 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | D. OPTIONAL COVERS | 0.0000 | 0.0000 | 0.1111 | 1.25 | 0.2500 | 0.1580 |
| 9 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4623 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.3992 |
| 10 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > the Policy Period | 0.0000 | 0.0000 | 0.2222 | 1.25 | 0.0000 | 0.2187 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 2: What is the maximum limit for ICU room charges under Star Health / HDFC Health Protector?
- **Expected Document**: HDFC
- **Expected Heading**: BENEFITS COVERED
- **Failure Category**: Ranking Failure

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.5026 | 15.3729 | 0.3636 | 1.00 | 0.0000 | 0.3463 |
| 2 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.5026 | 15.3729 | 0.3636 | 1.00 | 0.0000 | 0.3463 |
| 4 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 2 | ICU Charges means the amount charged by a Hospital towards | 0.4829 | 23.0922 | 0.3636 | 1.00 | 0.0000 | 0.3278 |
| 5 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 25 | % of Single Premium > Sum Assured on Death for other than Single Pay (i.e. for Limited Pay and Regular Pay) is the highest of the | 0.0000 | 0.0000 | 0.3636 | 1.25 | 0.0000 | 0.3075 |
| 6 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 32 | times the Annualized Premium > Page 32 of 65 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 7 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 32 | times the Annualized Premium > Page 32 of 65 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 8 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 11 | Benefit Description > Critical Illness Benefit Option (CIB) | 0.5440 | 16.7039 | 0.1818 | 1.00 | 0.0000 | 0.2788 |
| 9 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 11 | Benefit Description > Critical Illness Benefit Option (CIB) | 0.4976 | 0.0000 | 0.1818 | 1.00 | 0.0000 | 0.1970 |
| 10 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 11 | Benefit Description > Critical Illness Benefit Option (CIB) | 0.5440 | 16.7039 | 0.1818 | 1.00 | 0.0000 | 0.2788 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: The correct chunk was retrieved but ranked too low because: 
  * Top rank final score: 0.3463 (Vector: 0.5026, BM25: 15.3729, Meta: 0.3636, Coverage: 0.0000)
- **Suggested Fix**: Adjust reranking score factors or intent boost parameters based on the query category.

---

## Query 3: Does the policy cover advanced treatments like Severe Refractory Asthma?
- **Expected Document**: HDFC
- **Expected Heading**: BENEFITS COVERED
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | Uncontrolled Type 2 Diabetes > C.7 Modern Treatments/Advanced Procedures | 0.4740 | 20.7974 | 0.2500 | 1.25 | 0.0000 | 0.1718 |
| 2 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 9 | Filaria (Lymphatic Filariasis) > SBI General Insurance Company Limited | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 8 | Filaria (Lymphatic Filariasis) > SBI General Insurance Company Limited | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 4 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > or Section C.7 (Modern Treatments) or Section C.8 (AYUSH | 0.4868 | 13.9021 | 0.2500 | 1.25 | 0.0000 | 0.1655 |
| 5 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 8 | Zika Virus > Person, irrespective of Individual or Family Floater. The coverage | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 6 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 8 | Zika Virus > Person, irrespective of Individual or Family Floater. The coverage | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 7 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Treatment) or Section C.7 (Modern Treatments) or Section C.8 | 0.4726 | 14.2543 | 0.2500 | 1.25 | 0.0000 | 0.1630 |
| 8 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 8 | D. OPTIONAL COVERS > (Inpatient Hospitalization Treatment) or Section C.4 (Day Care | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | D. OPTIONAL COVERS | 0.0000 | 0.0000 | 0.1250 | 1.25 | 0.2500 | 0.0584 |
| 10 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4817 | 13.8486 | 0.2500 | 1.25 | 0.0000 | 0.1607 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 4: Can a POS Person sell this policy? What are their dos and don'ts?
- **Expected Document**: HDFC
- **Expected Heading**: POS Person
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 6 | GENERAL TERMS AND CONDITIONS > Person's death or payment of 100% Sum Insured. However, | 0.0000 | 14.0173 | 0.2000 | 1.00 | 0.0000 | 0.1110 |
| 2 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Expenses and Post-hospitalization Medical Expenses in | 0.0000 | 14.2048 | 0.2000 | 1.00 | 0.0000 | 0.1014 |
| 3 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | Uncontrolled Type 2 Diabetes > Conditions | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 4 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | Uncontrolled Type 2 Diabetes > Conditions | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 5 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 14 | No loans are available under this Policy Alterations > Page 14 of 41 | 0.0000 | 13.3596 | 0.2000 | 1.00 | 0.0000 | 0.0998 |
| 6 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 6 | GENERAL TERMS AND CONDITIONS > Person's death or payment of 100% Sum Insured. However, | 0.0000 | 12.2904 | 0.2000 | 1.00 | 0.0000 | 0.0988 |
| 7 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 5 | days maximum up to Age of 30 years and financially > Treatment of an Insured Person due to Illness or Injury sustained or | 0.0000 | 11.4367 | 0.2000 | 1.00 | 0.0000 | 0.0978 |
| 8 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > C.6 Bariatric Surgery Cover | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > C.6 Bariatric Surgery Cover | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 10 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 10 | Where only islets of langerhans are transplanted > Cover | 0.0000 | 16.1144 | 0.1000 | 1.00 | 0.0000 | 0.0775 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 5: Are organ donor expenses covered during transplant surgery?
- **Expected Document**: HDFC
- **Expected Heading**: Donor
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 10 | Major organ/bone marrow transplant | 0.4590 | 24.3827 | 0.2500 | 1.00 | 0.0000 | 0.1259 |
| 2 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 11 | Benign Brain Tumor | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 11 | Multiple Sclerosis with persisting symptoms > and | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 4 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 17 | ) BAUP- Board Approved Underwriting Policy > ➢ Major Organ /Bone Marrow Transplant | 0.0000 | 24.4085 | 0.2500 | 1.00 | 0.0000 | 0.1141 |
| 5 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 20 | consecutive days or > Page 20 of 65 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 6 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 20 | consecutive days or > Page 20 of 65 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 7 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 10 | Major organ/bone marrow transplant | 0.4706 | 21.6357 | 0.2500 | 1.00 | 0.0000 | 0.1138 |
| 8 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 11 | Multiple Sclerosis with persisting symptoms > I. The unequivocal diagnosis of Definite Multiple Sclerosis | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 11 | Multiple Sclerosis with persisting symptoms > I. The unequivocal diagnosis of Definite Multiple Sclerosis | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 10 | HDFC-Life-Click-2-Protect-Supreme-UIN101N183V01-Policy-Bond.pdf | 20 | consecutive days or > Page 20 of 65 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 6: What is the penalty if I fail to disclose a pre-existing medical condition?
- **Expected Document**: SBI
- **Expected Heading**: Terms and
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 17.1659 | 0.1429 | 1.00 | 0.0000 | 0.2036 |
| 2 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 17.1659 | 0.1429 | 1.00 | 0.0000 | 0.2036 |
| 4 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 8 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.0000 | 14.6963 | 0.1429 | 1.00 | 0.0000 | 0.1938 |
| 5 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 6 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 8 | SPACE FOR ENDORSEMENTS > Activities of Daily Living assessment confirms the inability of the Life Assured | 0.0000 | 14.6963 | 0.1429 | 1.00 | 0.0000 | 0.1938 |
| 7 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 30 | Life & CI Rebalance > Exclusions for Critical Illness Benefit | 0.4976 | 14.6504 | 0.0000 | 1.00 | 0.0000 | 0.1498 |
| 8 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 39 | Assignment or Transfer of Insurance Policies | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 36 | % 90% > Policy Term | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 10 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 5 | ) BAUP- Board Approved Underwriting Policy | 0.0000 | 28.7919 | 0.0000 | 1.00 | 0.0000 | 0.1399 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 7: Is there a co-pay requirement for senior citizens under HDFC Health Protector?
- **Expected Document**: HDFC
- **Expected Heading**: Co-pay
- **Failure Category**: Ranking Failure

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.5226 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.3262 |
| 2 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 10 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.5226 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.3262 |
| 4 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 3 | POLICY DOCUMENT- HDFC LIFE EASY HEALTH > Unique Identification Number: <<101N110V03>> | 0.5370 | 13.6516 | 0.2222 | 1.25 | 0.0000 | 0.3223 |
| 5 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.5110 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.3077 |
| 6 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.5110 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.3077 |
| 7 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.2877 |
| 8 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 9 | SPACE FOR ENDORSEMENTS > State or Medical Council of Indian Council or Council for Indian Medicine or for Homeopathy set up by | 0.0000 | 0.0000 | 0.3333 | 1.25 | 0.0000 | 0.2877 |
| 10 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 19 | Age Admitted | 0.5425 | 0.0000 | 0.2222 | 1.25 | 0.0000 | 0.2657 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: The correct chunk was retrieved but ranked too low because: 
  * Top rank final score: 0.3262 (Vector: 0.5226, BM25: 0.0000, Meta: 0.3333, Coverage: 0.0000)
- **Suggested Fix**: Adjust reranking score factors or intent boost parameters based on the query category.

---

## Query 8: Are OPD (Out-Patient) consults covered in this health policy?
- **Expected Document**: HDFC
- **Expected Heading**: Exclusions
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > C.4 Day Care Treatment | 0.4884 | 0.0000 | 0.2857 | 1.25 | 0.0000 | 0.3584 |
| 2 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > A. Greater than or equal to 40 or | 0.0000 | 0.0000 | 0.1429 | 1.25 | 0.0000 | 0.1314 |
| 3 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > Schedule, if the Medically Necessary Hospitalization exceeds 24 | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 4 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 16 | Eisenmenger's Syndrome > the Policy Schedule for the OPD expenses including Diagnostics and | 0.5598 | 12.3598 | 0.2857 | 1.25 | 0.0000 | 0.3523 |
| 5 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 17 | Eisenmenger's Syndrome > Hospitalization of the female Insured Person for the delivery of the | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 6 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 17 | Eisenmenger's Syndrome > Hospitalization of the female Insured Person for the delivery of the | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 7 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 3 | OPD Treatment means the one in which the Insured visits a clinic / | 0.5798 | 13.2862 | 0.2857 | 1.00 | 0.0000 | 0.3413 |
| 8 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 6 | B. SCOPE OF COVER > Care Treatment) or Section C.7 (Modern Treatments) or C.8 | 0.4962 | 0.0000 | 0.2857 | 1.25 | 0.0000 | 0.3274 |
| 9 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > the Policy Period | 0.0000 | 0.0000 | 0.1429 | 1.00 | 0.0000 | 0.1288 |
| 10 | Health_Edge_Insurance_Policy_wording_75e1ad1343.pdf | 7 | B. SCOPE OF COVER > D.1 Domestic Help/Staff Indemnity | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 9: What are the entry age limits for SBI Saral Suraksha Bima?
- **Expected Document**: SBI
- **Expected Heading**: Eligibility
- **Failure Category**: Wrong Policy Routing

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 1 | DEFINITIONS > In-Patient Care means treatment for which the insured person | 0.5106 | 0.0000 | 0.7000 | 1.00 | 0.0000 | 0.5221 |
| 2 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 1 | PREAMBLE > Age means age of the Insured person on last birthday as on date | 0.5698 | 10.6289 | 0.6000 | 1.00 | 0.0000 | 0.5100 |
| 3 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 2 | Loss of Index finger – > Senior Citizen means any person, who has attained the Age of | 0.5396 | 9.7330 | 0.6000 | 1.00 | 0.0000 | 0.4971 |
| 4 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 1 | PREAMBLE > Cumulative Bonus means any increase or addition in the Sum | 0.5730 | 10.5701 | 0.5000 | 1.00 | 0.0000 | 0.4804 |
| 5 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 5 | EXCLUSIONS (applicable to all sections of the policy) > SBI General Insurance Company Limited > Basic documents required for All claims, | 0.0000 | 0.0000 | 0.6000 | 1.00 | 0.0000 | 0.4542 |
| 6 | SARAL_SURAKSHA_BIMA_Policy_Wording_d06ae350e3.pdf | 3 | COVERAGE > or Permanent Total Disablement or Permanent Partial | 0.0000 | 0.0000 | 0.5000 | 1.00 | 0.0000 | 0.4397 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: Policy routing bias is failing. The query contains keywords for one carrier/product, but the retriever routed the query to a different carrier/product because of lexical or vector score overlap without sufficient bias boost.
- **Suggested Fix**: Build a generic alias normalization layer that recognizes common spelling variants of carrier and product names (e.g. SBI Ergo, SBIG, State Bank, HDFC Ergo) and boosts chunks from the matched policy by a higher soft bias multiplier.

---

## Query 10: Are diagnostic tests covered if hospitalization is not required?
- **Expected Document**: HDFC
- **Expected Heading**: Exclusions
- **Failure Category**: Ranking Failure

### Top Retrieved Chunks:
| Rank | Filename | Page | Heading | Vector | BM25 | Meta | Intent Boost | Boilerplate Penalty | Final Score |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Hospitalization and/or Surgery is/are not in accordance with the diagnosis and treatment of the | 0.4515 | 22.5854 | 0.4286 | 1.00 | 0.0000 | 0.4205 |
| 2 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Any condition with respect to the covered benefits, for which the Life Assured had signs or | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 3 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Hospitalization and/or Surgery is/are not in accordance with the diagnosis and treatment of the | 0.4515 | 22.5854 | 0.4286 | 1.00 | 0.0000 | 0.4205 |
| 4 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 14 | Claims Procedure > Operating Theatre Notes (for Surgical Cash benefit) | 0.0000 | 13.7623 | 0.1429 | 1.00 | 0.0000 | 0.1938 |
| 5 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 8 | times of the Annualized Premium; or > B. Critical Illness Benefit: On diagnosis of any of the covered Critical Illnesses, the applicable Critical Illness | 0.0000 | 15.0469 | 0.1429 | 1.00 | 0.0000 | 0.1698 |
| 6 | HDFC-Life-Click-2-Protect-Life-V08-Policy-Bond.pdf | 29 | Life & CI Rebalance > Page 29 of 41 > Fulminant Viral Hepatitis | 0.0000 | 17.6258 | 0.0000 | 1.00 | 0.0000 | 0.1643 |
| 7 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Routine eye tests, any Dental Treatment or Surgery of cosmetic nature, extraction of impacted | 0.0000 | 13.3070 | 0.1429 | 1.00 | 0.0000 | 0.1628 |
| 8 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Hospitalization and/or Surgery relating to infertility or impotency, sex change or any treatment | 0.0000 | 0.0000 | 0.0000 | 1.00 | 0.0000 | 0.0000 |
| 9 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 18 | Routine eye tests, any Dental Treatment or Surgery of cosmetic nature, extraction of impacted | 0.0000 | 13.3070 | 0.1429 | 1.00 | 0.0000 | 0.1628 |
| 10 | HDFC-Life-Easy-Health-101N110V03-Policy-Bond-Regular-Pay.pdf | 14 | Claims Procedure > Operating Theatre Notes (for Surgical Cash benefit) | 0.4945 | 0.0000 | 0.1429 | 1.00 | 0.0000 | 0.1565 |

### Root Cause Analysis & Proposed Fix:
- **Root Cause**: The correct chunk was retrieved but ranked too low because: 
  * Top rank final score: 0.4205 (Vector: 0.4515, BM25: 22.5854, Meta: 0.4286, Coverage: 0.0000)
- **Suggested Fix**: Adjust reranking score factors or intent boost parameters based on the query category.

---

