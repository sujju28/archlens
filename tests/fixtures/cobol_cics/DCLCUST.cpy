      ******************************************************************
      * DCLGEN TABLE CUSTOMER
      ******************************************************************
           EXEC SQL DECLARE CUSTOMER TABLE
           ( CUSTNO         CHAR(10) NOT NULL,
             CUSTNAME       VARCHAR(40),
             WAREHOUSE_ID   INTEGER
           ) END-EXEC.
       01  DCLCUSTOMER.
           10 CUSTNO              PIC X(10).
           10 CUSTNAME            PIC X(40).
           10 WAREHOUSE-ID        PIC S9(9) COMP.
