       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUSTINQ.
      * Customer inquiry screen — validates account before link.
       ENVIRONMENT DIVISION.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       COPY CUSTCPY.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-RECEIVE
           IF WS-ACCT-STATUS = 'C'
              PERFORM 2000-LINK
           END-IF
           PERFORM 3000-SEND
           GOBACK.
       1000-RECEIVE.
           EXEC CICS RECEIVE MAP('CUSTMAP') END-EXEC.
       2000-LINK.
           EXEC CICS LINK PROGRAM('CUSTSVC') END-EXEC.
       3000-SEND.
           EXEC CICS SEND MAP('CUSTMAP') END-EXEC.
