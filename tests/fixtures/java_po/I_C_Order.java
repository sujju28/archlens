package org.compiere.model;

/** Generated Interface for C_Order */
public interface I_C_Order
{
	String Table_Name = "C_Order";

	String COLUMNNAME_C_Order_ID = "C_Order_ID";
	String COLUMNNAME_C_BPartner_ID = "C_BPartner_ID";
	String COLUMNNAME_M_Warehouse_ID = "M_Warehouse_ID";
	String COLUMNNAME_DocStatus = "DocStatus";

	int getC_Order_ID();
	int getC_BPartner_ID();
	int getM_Warehouse_ID();
	String getDocStatus();
}
